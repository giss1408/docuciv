"""Smoke tests de la file de revue de l'agent émetteur (roadmap Phase 2)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from conftest import owner_exec
from helpers import Found, MemoryStorage, StubScanner, jpeg_with_exif
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db import tenant_session, user_session
from app.main import app
from app.models import (
    AdminAgent,
    Administration,
    AdministrationRole,
    AgentRole,
    DocumentRequest,
    DocumentRequestStatusHistory,
    NotificationChannel,
    NotificationEvent,
    RequestStatus,
    ReviewStatus,
    SourceEvidence,
    TenantStatus,
    User,
    UserType,
)
from app.services.antivirus import get_scanner
from app.services.reference_check import get_reference_checker
from app.services.review import add_business_days, enter_review_if_ready
from app.services.state_machine import transition
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


async def tenant(
    agent_role: AgentRole = AgentRole.issuer_agent,
    admin_role: AdministrationRole = AdministrationRole.issuer,
    status: TenantStatus = TenantStatus.active,
) -> tuple[uuid.UUID, dict[str, str]]:
    tid, aid = uuid.uuid4(), uuid.uuid4()
    async with tenant_session(tid) as s:
        s.add(Administration(id=tid, name="Mairie", role=admin_role, status=status))
        await s.flush()
        s.add(AdminAgent(id=aid, tenant_id=tid, full_name="Koffi", email="k@x.ci", role=agent_role))
    return tid, {"X-Dev-Agent-Id": str(aid), "X-Dev-Tenant-Id": str(tid)}


async def citizen_request(
    storage: MemoryStorage, tid: uuid.UUID, *, with_evidence: bool = True
) -> tuple[uuid.UUID, uuid.UUID, dict[str, str]]:
    uid = uuid.uuid4()
    async with user_session(uid) as s:
        s.add(User(id=uid, type=UserType.citizen, full_name="Awa", phone="+2250100000000"))
    h = {"X-Dev-User-Id": str(uid)}
    async with client() as c:
        r = await c.post(
            "/requests",
            json={
                "administration_id": str(tid),
                "document_type": "acte_naissance",
                "reference_document_id": "AN-1998-004512",
            },
            headers=h,
        )
        rid = uuid.UUID(r.json()["id"])
        if with_evidence:
            await upload_evidence(c, storage, rid, h)
    return rid, uid, h


async def upload_evidence(
    c: AsyncClient, storage: MemoryStorage, rid: uuid.UUID, h: dict[str, str]
) -> uuid.UUID:
    data = jpeg_with_exif()
    r = await c.post(
        f"/requests/{rid}/evidence/upload-url",
        json={"mime_type": "image/jpeg", "file_size_bytes": len(data)},
        headers=h,
    )
    eid = r.json()["evidence_id"]
    storage.objects[storage.presigned[-1][0]] = data
    done = await c.post(f"/requests/{rid}/evidence/{eid}/complete", headers=h)
    assert done.status_code == 200
    return uuid.UUID(eid)


async def pay(tid: uuid.UUID, rid: uuid.UUID) -> None:
    """Simule la confirmation de paiement (le vrai webhook arrive en Phase 3)."""
    async with tenant_session(tid) as s:
        await transition(s, rid, RequestStatus.pending_payment, RequestStatus.paid)
        await enter_review_if_ready(s, rid)


async def in_review(
    storage: MemoryStorage, tid: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    rid, uid, _ = await citizen_request(storage, tid)
    await pay(tid, rid)
    async with tenant_session(tid) as s:
        eid = (await s.scalars(select(SourceEvidence.id))).one()
        assert (await s.get(DocumentRequest, rid)).status == RequestStatus.in_review  # type: ignore[union-attr]
    return rid, eid, uid


async def request_status(tid: uuid.UUID, rid: uuid.UUID) -> DocumentRequest:
    async with tenant_session(tid) as s:
        req = await s.get(DocumentRequest, rid)
        assert req is not None
        return req


# --- passage automatique en in_review -------------------------------------------------------


async def test_evidence_then_payment_enters_review(storage: MemoryStorage) -> None:
    tid, _ = await tenant()
    rid, _, _ = await citizen_request(storage, tid)
    assert (await request_status(tid, rid)).status == RequestStatus.pending_payment
    await pay(tid, rid)
    assert (await request_status(tid, rid)).status == RequestStatus.in_review


async def test_payment_then_evidence_enters_review(storage: MemoryStorage) -> None:
    tid, _ = await tenant()
    rid, _, h = await citizen_request(storage, tid, with_evidence=False)
    await pay(tid, rid)
    assert (await request_status(tid, rid)).status == RequestStatus.paid  # pas de pièce: attend
    async with client() as c:
        await upload_evidence(c, storage, rid, h)
    assert (await request_status(tid, rid)).status == RequestStatus.in_review


def test_add_business_days_skips_weekend() -> None:
    friday = datetime(2026, 11, 6, 10, tzinfo=UTC)
    assert add_business_days(friday, 1).date().isoformat() == "2026-11-09"
    assert add_business_days(friday, 5).date().isoformat() == "2026-11-13"


# --- accès et file --------------------------------------------------------------------------


async def test_queue_lists_only_own_tenant(storage: MemoryStorage) -> None:
    ta, ha = await tenant()
    tb, hb = await tenant()
    ra, _, _ = await in_review(storage, ta)
    rb, _, _ = await in_review(storage, tb)
    async with client() as c:
        a = (await c.get("/issuer/requests", headers=ha)).json()
        b = (await c.get("/issuer/requests?status=in_review", headers=hb)).json()
    assert [x["id"] for x in a] == [str(ra)] and [x["id"] for x in b] == [str(rb)]
    assert set(a[0]) == {
        "id",
        "status",
        "document_type",
        "reference_document_id",
        "reference_check",
        "created_at",
    }  # pas de PII ni de payload


async def test_queue_access_control() -> None:
    _, verifier = await tenant(agent_role=AgentRole.verifier_agent)
    _, verifier_tenant = await tenant(admin_role=AdministrationRole.verifier)
    _, suspended = await tenant(status=TenantStatus.suspended)
    tid, good = await tenant()
    wrong_tenant = {**good, "X-Dev-Tenant-Id": str(uuid.uuid4())}
    async with client() as c:
        assert (await c.get("/issuer/requests")).status_code == 401
        assert (await c.get("/issuer/requests", headers=wrong_tenant)).status_code == 401
        for h in (verifier, verifier_tenant, suspended):
            assert (await c.get("/issuer/requests", headers=h)).status_code == 403
        assert (
            await c.get("/issuer/requests?status=pending_payment", headers=good)
        ).status_code == 422
        assert (await c.get("/issuer/requests", headers=good)).status_code == 200


async def test_agent_of_tenant_a_cannot_use_tenant_b_header() -> None:
    _, ha = await tenant()
    tb, _ = await tenant()
    forged = {"X-Dev-Agent-Id": ha["X-Dev-Agent-Id"], "X-Dev-Tenant-Id": str(tb)}
    async with client() as c:
        assert (await c.get("/issuer/requests", headers=forged)).status_code == 401


# --- consultation de la pièce ---------------------------------------------------------------


async def test_view_evidence_short_lived_url_and_isolation(storage: MemoryStorage) -> None:
    ta, ha = await tenant()
    _, hb = await tenant()
    rid, eid, _ = await in_review(storage, ta)
    async with client() as c:
        r = await c.get(f"/issuer/requests/{rid}/evidence", headers=ha)
        other = await c.get(f"/issuer/requests/{rid}/evidence", headers=hb)
    assert r.status_code == 200
    item = r.json()[0]
    assert item["evidence_id"] == str(eid) and item["expires_in"] == 120
    assert item["view_url"].endswith("?ttl=120") and item["mime_type"] == "image/jpeg"
    assert other.status_code == 404


# --- décision -------------------------------------------------------------------------------


async def test_accept_moves_to_in_progress_with_estimate_and_notifies(
    storage: MemoryStorage,
) -> None:
    tid, h = await tenant()
    await owner_exec(
        f"INSERT INTO processing_delay_configs (id, administration_id, document_type, business_days)"
        f" VALUES (gen_random_uuid(), '{tid}', 'acte_naissance', 2)"
    )
    rid, eid, uid = await in_review(storage, tid)
    async with client() as c:
        r = await c.post(
            f"/issuer/requests/{rid}/evidence/{eid}/review",
            json={"decision": "accepted"},
            headers=h,
        )
    assert r.status_code == 200 and r.json()["request_status"] == "in_progress"

    req = await request_status(tid, rid)
    assert req.status == RequestStatus.in_progress
    assert req.estimated_ready_at is not None
    delta = req.estimated_ready_at - datetime.now(UTC)
    assert timedelta(days=1, hours=20) < delta < timedelta(days=5)  # 2 jours ouvrés (config tenant)
    async with tenant_session(tid) as s:
        ev = await s.get(SourceEvidence, eid)
        assert ev is not None and ev.review_status == ReviewStatus.accepted
        assert ev.reviewed_by == uuid.UUID(h["X-Dev-Agent-Id"])
        hist = (
            await s.scalars(
                select(DocumentRequestStatusHistory)
                .where(DocumentRequestStatusHistory.document_request_id == rid)
                .order_by(DocumentRequestStatusHistory.changed_at)
            )
        ).all()
        events = {
            (e.event_type, e.channel)
            for e in await s.scalars(
                select(NotificationEvent).where(NotificationEvent.document_request_id == rid)
            )
        }
    assert [x.to_status for x in hist][-2:] == [RequestStatus.in_review, RequestStatus.in_progress]
    assert {
        ("processing_started", NotificationChannel.email),
        ("processing_started", NotificationChannel.sms),
    } <= events


async def test_accept_uses_default_delay_without_tenant_config(storage: MemoryStorage) -> None:
    tid, h = await tenant()
    rid, eid, _ = await in_review(storage, tid)
    async with client() as c:
        await c.post(
            f"/issuer/requests/{rid}/evidence/{eid}/review",
            json={"decision": "accepted"},
            headers=h,
        )
    delta = (await request_status(tid, rid)).estimated_ready_at - datetime.now(UTC)  # type: ignore[operator]
    assert timedelta(days=4, hours=20) < delta < timedelta(days=8)


async def test_reject_requires_notes_then_rejects_and_notifies(storage: MemoryStorage) -> None:
    tid, h = await tenant()
    rid, eid, uid = await in_review(storage, tid)
    url = f"/issuer/requests/{rid}/evidence/{eid}/review"
    async with client() as c:
        assert (await c.post(url, json={"decision": "rejected"}, headers=h)).status_code == 422
        assert (
            await c.post(url, json={"decision": "rejected", "review_notes": "  "}, headers=h)
        ).status_code == 422
        r = await c.post(
            url, json={"decision": "rejected", "review_notes": "Photo illisible"}, headers=h
        )
    assert r.status_code == 200 and r.json()["request_status"] == "rejected"
    req = await request_status(tid, rid)
    assert req.status == RequestStatus.rejected and req.rejection_reason == "Photo illisible"
    async with tenant_session(tid) as s:
        ev = await s.get(SourceEvidence, eid)
        assert ev is not None and ev.review_status == ReviewStatus.rejected
        assert ev.review_notes == "Photo illisible"
    async with user_session(uid) as s:
        events = {
            (e.event_type, e.channel)
            for e in await s.scalars(
                select(NotificationEvent).where(NotificationEvent.document_request_id == rid)
            )
        }
    assert {
        ("evidence_rejected_review", NotificationChannel.email),
        ("evidence_rejected_review", NotificationChannel.sms),
    } <= events


async def test_cannot_review_twice_or_out_of_state(storage: MemoryStorage) -> None:
    tid, h = await tenant()
    rid, eid, _ = await in_review(storage, tid)
    url = f"/issuer/requests/{rid}/evidence/{eid}/review"
    async with client() as c:
        assert (await c.post(url, json={"decision": "accepted"}, headers=h)).status_code == 200
        assert (await c.post(url, json={"decision": "accepted"}, headers=h)).status_code == 409
        assert (
            await c.post(url, json={"decision": "rejected", "review_notes": "x"}, headers=h)
        ).status_code == 409
    # pièce validée mais demande pas encore payée: non instruisible
    rid2, _, _ = await citizen_request(storage, tid)
    async with tenant_session(tid) as s:
        eid2 = (
            await s.scalars(
                select(SourceEvidence.id).where(SourceEvidence.document_request_id == rid2)
            )
        ).one()
    async with client() as c:
        r = await c.post(
            f"/issuer/requests/{rid2}/evidence/{eid2}/review",
            json={"decision": "accepted"},
            headers=h,
        )
    assert r.status_code == 409


async def test_other_tenant_cannot_review(storage: MemoryStorage) -> None:
    ta, _ = await tenant()
    _, hb = await tenant()
    rid, eid, _ = await in_review(storage, ta)
    async with client() as c:
        r = await c.post(
            f"/issuer/requests/{rid}/evidence/{eid}/review",
            json={"decision": "accepted"},
            headers=hb,
        )
    assert r.status_code == 404
    assert (await request_status(ta, rid)).status == RequestStatus.in_review
