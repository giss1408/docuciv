"""Smoke tests GET /requests et GET /requests/{id} (timeline, notifications.md §5)."""

import uuid

import pytest
from helpers import Found, MemoryStorage, StubScanner
from httpx import ASGITransport, AsyncClient
from test_issuer import citizen_request, in_review, pay, tenant, upload_evidence

from app.main import app
from app.services.antivirus import get_scanner
from app.services.reference_check import get_reference_checker
from app.services.storage import get_storage

pytestmark = pytest.mark.usefixtures("migrated_db")


@pytest.fixture
def storage():  # type: ignore[no-untyped-def]
    s = MemoryStorage()
    app.dependency_overrides[get_storage] = lambda: s
    app.dependency_overrides[get_scanner] = lambda: StubScanner()
    app.dependency_overrides[get_reference_checker] = lambda: Found()
    yield s
    app.dependency_overrides.clear()


def client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def get(path: str, headers: dict[str, str] | None = None):  # type: ignore[no-untyped-def]
    async with client() as c:
        return await c.get(path, headers=headers or {})


async def test_timeline_follows_the_whole_flow(storage: MemoryStorage) -> None:
    tid, agent = await tenant()
    rid, _, h = await citizen_request(storage, tid, with_evidence=False)

    body = (await get(f"/requests/{rid}", h)).json()
    assert body["status"] == "pending_payment" and body["evidence_review_status"] is None
    assert [x["to_status"] for x in body["history"]] == [
        "pending_reference_check",
        "pending_payment",
    ]

    async with client() as c:
        await upload_evidence(c, storage, rid, h)
    await pay(tid, rid)
    body = (await get(f"/requests/{rid}", h)).json()
    assert body["status"] == "in_review" and body["evidence_review_status"] == "pending"

    async with client() as c:
        eid = (await c.get(f"/issuer/requests/{rid}/evidence", headers=agent)).json()[0][
            "evidence_id"
        ]
        await c.post(
            f"/issuer/requests/{rid}/evidence/{eid}/review",
            json={"decision": "accepted"},
            headers=agent,
        )
    body = (await get(f"/requests/{rid}", h)).json()
    assert body["status"] == "in_progress" and body["evidence_review_status"] == "accepted"
    assert body["estimated_ready_at"] is not None
    assert [x["to_status"] for x in body["history"]] == [
        "pending_reference_check",
        "pending_payment",
        "paid",
        "in_review",
        "in_progress",
    ]
    stamps = [x["changed_at"] for x in body["history"]]
    assert stamps == sorted(stamps)


async def test_rejection_reason_visible_but_internal_reasons_are_not(
    storage: MemoryStorage,
) -> None:
    tid, agent = await tenant()
    rid, eid, _ = await in_review(storage, tid)
    async with client() as c:
        await c.post(
            f"/issuer/requests/{rid}/evidence/{eid}/review",
            json={"decision": "rejected", "review_notes": "Photo illisible"},
            headers=agent,
        )
    # l'identifiant citoyen est dans la fixture de in_review; on le retrouve via la requête
    from sqlalchemy import select

    from app.db import tenant_session
    from app.models import DocumentRequest

    async with tenant_session(tid) as s:
        uid = (
            await s.scalars(select(DocumentRequest.user_id).where(DocumentRequest.id == rid))
        ).one()
    r = await get(f"/requests/{rid}", {"X-Dev-User-Id": str(uid)})
    body = r.json()
    assert body["status"] == "rejected" and body["rejection_reason"] == "Photo illisible"
    assert body["evidence_review_status"] == "rejected"
    assert all(set(x) == {"to_status", "changed_at"} for x in body["history"])  # pas de `reason`


async def test_other_citizen_gets_404_and_unauthenticated_401(storage: MemoryStorage) -> None:
    tid, _ = await tenant()
    rid, _, _ = await citizen_request(storage, tid, with_evidence=False)
    _, _, other = await citizen_request(storage, tid, with_evidence=False)
    assert (await get(f"/requests/{rid}", other)).status_code == 404
    assert (await get(f"/requests/{uuid.uuid4()}", other)).status_code == 404
    assert (await get(f"/requests/{rid}")).status_code == 401
    assert (await get("/requests")).status_code == 401
    assert (await get("/requests/not-a-uuid", other)).status_code == 422


async def test_list_returns_only_own_requests_newest_first_with_pagination(
    storage: MemoryStorage,
) -> None:
    tid, _ = await tenant()
    first, uid, h = await citizen_request(storage, tid, with_evidence=False)
    async with client() as c:
        ids = [str(first)]
        for _ in range(2):
            r = await c.post(
                "/requests",
                json={
                    "administration_id": str(tid),
                    "document_type": "car",
                    "reference_document_id": "CAR-0001",
                },
                headers=h,
            )
            ids.append(r.json()["id"])
    _, _, other = await citizen_request(storage, tid, with_evidence=False)

    mine = (await get("/requests", h)).json()
    assert [x["id"] for x in mine] == list(reversed(ids))
    assert set(mine[0]) == {
        "id",
        "status",
        "document_type",
        "reference_document_id",
        "estimated_ready_at",
        "created_at",
        "updated_at",
    }
    assert len((await get("/requests", other)).json()) == 1
    page = (await get("/requests?limit=1&offset=1", h)).json()
    assert [x["id"] for x in page] == [ids[1]]
    assert (await get("/requests?limit=101", h)).status_code == 422
