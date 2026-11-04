"""Smoke tests des réclamations (notifications.md §6, roadmap Phase 2)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from conftest import owner_exec
from helpers import MemoryStorage
from httpx import Response
from sqlalchemy import select
from test_issuer import citizen_request, client, storage, tenant  # noqa: F401

from app.db import tenant_session, user_session
from app.models import (
    NotificationChannel,
    NotificationEvent,
    Reclamation,
    ReclamationStatus,
    User,
    UserType,
)

pytestmark = pytest.mark.usefixtures("migrated_db")

DESC = "Ma demande est en traitement depuis 10 jours, le délai annoncé était de 5 jours."


async def citizen() -> tuple[uuid.UUID, dict[str, str]]:
    uid = uuid.uuid4()
    async with user_session(uid) as s:
        s.add(User(id=uid, type=UserType.citizen, full_name="Awa", phone="+2250100000000"))
    return uid, {"X-Dev-User-Id": str(uid)}


async def file_claim(h: dict[str, str], rid: uuid.UUID | None, category: str = "delay") -> Response:
    async with client() as c:
        return await c.post(
            "/reclamations",
            json={
                "document_request_id": str(rid) if rid else None,
                "category": category,
                "description": DESC,
            },
            headers=h,
        )


async def events(uid: uuid.UUID, kind: str) -> list[NotificationEvent]:
    async with user_session(uid) as s:
        return list(
            await s.scalars(select(NotificationEvent).where(NotificationEvent.event_type == kind))
        )


async def test_create_acknowledges_with_sla_and_notifies(storage: MemoryStorage) -> None:  # noqa: F811
    tid, _ = await tenant()
    rid, uid, h = await citizen_request(storage, tid)
    r = await file_claim(h, rid)
    assert r.status_code == 201 and r.json()["status"] == "open"
    due = datetime.fromisoformat(r.json()["sla_response_due_at"])
    assert timedelta(hours=47) < due - datetime.now(UTC) < timedelta(hours=49)
    assert {e.channel for e in await events(uid, "reclamation_received")} == {
        NotificationChannel.email,
        NotificationChannel.sms,
    }
    pay = await file_claim(h, rid, "payment_issue")  # SLA prioritaire
    pay_due = datetime.fromisoformat(pay.json()["sla_response_due_at"])
    assert pay_due - datetime.now(UTC) < timedelta(hours=25)


async def test_free_reclamation_without_request_is_accepted() -> None:
    uid, h = await citizen()
    r = await file_claim(h, None, "other")
    assert r.status_code == 201
    assert len(await events(uid, "reclamation_received")) == 2


async def test_cannot_claim_on_someone_elses_request(storage: MemoryStorage) -> None:  # noqa: F811
    tid, _ = await tenant()
    rid, _, _ = await citizen_request(storage, tid)
    _, other = await citizen()
    assert (await file_claim(other, rid)).status_code == 404
    assert (await file_claim(other, uuid.uuid4())).status_code == 404


async def test_validation_and_auth() -> None:
    _, h = await citizen()
    async with client() as c:
        short = await c.post(
            "/reclamations", json={"category": "delay", "description": "ko"}, headers=h
        )
        bad_cat = await c.post(
            "/reclamations", json={"category": "nope", "description": DESC}, headers=h
        )
        anon = await c.post("/reclamations", json={"category": "delay", "description": DESC})
    assert (short.status_code, bad_cat.status_code, anon.status_code) == (422, 422, 401)


async def test_full_cycle_open_resolved_reopened_resolved(storage: MemoryStorage) -> None:  # noqa: F811
    tid, ha = await tenant()
    rid, uid, h = await citizen_request(storage, tid)
    cid = (await file_claim(h, rid)).json()["id"]
    async with client() as c:
        queue = (await c.get("/issuer/reclamations", headers=ha)).json()
        assert [x["id"] for x in queue] == [cid]

        res = await c.post(
            f"/issuer/reclamations/{cid}/respond",
            json={"status": "resolved", "response": "Document émis ce jour."},
            headers=ha,
        )
        assert res.status_code == 200 and res.json()["status"] == "resolved"
        assert len(await events(uid, "reclamation_answered")) == 2  # email + sms
        # Plus dans la file ouverte; une seconde réponse est refusée.
        assert (await c.get("/issuer/reclamations", headers=ha)).json() == []
        again = await c.post(
            f"/issuer/reclamations/{cid}/respond",
            json={"status": "rejected", "response": "x"},
            headers=ha,
        )
        assert again.status_code == 409

        mine = (await c.get("/reclamations", headers=h)).json()
        assert mine[0]["response"] == "Document émis ce jour."
        assert "handled_by" not in mine[0]

        reopened = await c.post(f"/reclamations/{cid}/reopen", headers=h)
        assert reopened.json()["status"] == "reopened"
        assert (await c.post(f"/reclamations/{cid}/reopen", headers=h)).status_code == 409
        assert len((await c.get("/issuer/reclamations", headers=ha)).json()) == 1
        await c.post(
            f"/issuer/reclamations/{cid}/respond",
            json={"status": "resolved", "response": "Après vérification, c'est réglé."},
            headers=ha,
        )
    assert len(await events(uid, "reclamation_answered")) == 4  # 2e réponse notifiée aussi


async def test_reopen_window_expires(storage: MemoryStorage) -> None:  # noqa: F811
    tid, ha = await tenant()
    rid, _, h = await citizen_request(storage, tid)
    cid = (await file_claim(h, rid)).json()["id"]
    async with client() as c:
        await c.post(
            f"/issuer/reclamations/{cid}/respond",
            json={"status": "rejected", "response": "Non fondée."},
            headers=ha,
        )
    await owner_exec(
        f"UPDATE reclamations SET updated_at = now() - interval '30 days' WHERE id = '{cid}'"
    )
    async with client() as c:
        r = await c.post(f"/reclamations/{cid}/reopen", headers=h)
    assert r.status_code == 409 and r.json()["detail"] == "reopen_window_expired"


async def test_cross_tenant_and_cross_citizen_isolation(storage: MemoryStorage) -> None:  # noqa: F811
    ta, ha = await tenant()
    tb, hb = await tenant()
    ra, _, h1 = await citizen_request(storage, ta)
    cid = (await file_claim(h1, ra)).json()["id"]
    _, h2 = await citizen()
    free = (await file_claim(h1, None, "other")).json()["id"]
    async with client() as c:
        # Tenant B: ne voit rien et ne peut pas répondre (404, pas 403: pas d'énumération).
        assert (await c.get("/issuer/reclamations", headers=hb)).json() == []
        r = await c.post(
            f"/issuer/reclamations/{cid}/respond",
            json={"status": "resolved", "response": "intrusion"},
            headers=hb,
        )
        assert r.status_code == 404
        # La réclamation libre n'est visible d'aucun tenant.
        ids = [x["id"] for x in (await c.get("/issuer/reclamations", headers=ha)).json()]
        assert ids == [cid] and free not in ids
        # Autre citoyen: liste vide, réouverture impossible.
        assert (await c.get("/reclamations", headers=h2)).json() == []
        assert (await c.post(f"/reclamations/{cid}/reopen", headers=h2)).status_code == 404
    async with tenant_session(tb) as s:
        assert list(await s.scalars(select(Reclamation))) == []
    async with tenant_session(ta) as s:
        claim = await s.get(Reclamation, uuid.UUID(cid))
        assert claim is not None and claim.status == ReclamationStatus.open
