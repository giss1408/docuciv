"""Smoke tests de l'outbox WhatsApp (démo) et du rendu des messages."""

import uuid
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest
from helpers import MemoryStorage
from sqlalchemy import select
from test_issuer import citizen_request, client, in_review, pay, storage, tenant  # noqa: F401

from app.db import tenant_session
from app.models import DocumentType, NotificationChannel, NotificationEvent, NotificationSendStatus
from app.services import dispatch
from app.services.messages import MessageContext, french_date, render_message, whatsapp_url
from app.services.notifications import EventType

CTX = MessageContext(
    request_id=uuid.UUID("12345678-aaaa-bbbb-cccc-1234567890ab"),
    document_type=DocumentType.acte_naissance,
    administration="Mairie de Cocody",
    estimated_ready_at=datetime(2026, 11, 12, tzinfo=UTC),
    rejection_reason="photo illisible",
)


@pytest.mark.parametrize("event", list(EventType))
def test_every_event_has_a_message_without_pii(event: EventType) -> None:
    msg = render_message(event, CTX)
    assert msg.startswith("DocuCiv : ")
    assert "Awa" not in msg and "+225" not in msg


def test_message_content() -> None:
    assert "12 novembre 2026" in render_message(EventType.processing_started, CTX)
    assert "extrait d'acte de naissance" in render_message(EventType.processing_started, CTX)
    assert "photo illisible" in render_message(EventType.evidence_rejected_review, CTX)
    assert french_date(datetime(2026, 8, 1, tzinfo=UTC)) == "1 août 2026"


def test_whatsapp_url() -> None:
    url = whatsapp_url("+225 01 00 00 00 00", "Bonjour & merci")
    assert url is not None and urlparse(url).path == "/2250100000000"
    assert parse_qs(urlparse(url).query)["text"] == ["Bonjour & merci"]
    assert whatsapp_url("abc", "x") is None


pytestmark_db = pytest.mark.usefixtures("migrated_db")


async def accepted_request(storage: MemoryStorage, tid: uuid.UUID, h: dict[str, str]):  # type: ignore[no-untyped-def]  # noqa: F811
    rid, eid, uid = await in_review(storage, tid)
    async with client() as c:
        r = await c.post(
            f"/issuer/requests/{rid}/evidence/{eid}/review",
            json={"decision": "accepted"},
            headers=h,
        )
    assert r.status_code == 200
    return rid, uid


@pytestmark_db
async def test_outbox_prefilled_whatsapp_then_ack(storage: MemoryStorage) -> None:  # noqa: F811
    tid, ha = await tenant()
    rid, _ = await accepted_request(storage, tid, ha)
    async with client() as c:
        items = (await c.get("/issuer/outbox", headers=ha)).json()
        mine = [i for i in items if i["request_id"] == str(rid)]
        assert [i["event_type"] for i in mine] == ["processing_started"]
        item = mine[0]
        assert item["to_send"] is True
        assert "Mairie" in item["message"] and "extrait d'acte de naissance" in item["message"]
        assert item["whatsapp_url"].startswith("https://wa.me/2250100000000?text=")
        assert "Awa" not in item["message"]  # pas de nom du citoyen dans le message

        ack = await c.post(f"/issuer/outbox/{item['event_id']}/ack", headers=ha)
        assert ack.status_code == 204
        assert (await c.get("/issuer/outbox", headers=ha)).json() == []
        history = (await c.get("/issuer/outbox?pending_only=false", headers=ha)).json()
        assert [i["to_send"] for i in history] == [False]
        again = await c.post(f"/issuer/outbox/{item['event_id']}/ack", headers=ha)
        assert again.status_code == 404  # déjà acquitté


@pytestmark_db
async def test_outbox_is_tenant_isolated(storage: MemoryStorage) -> None:  # noqa: F811
    ta, ha = await tenant()
    _, hb = await tenant()
    await accepted_request(storage, ta, ha)
    async with client() as c:
        assert (await c.get("/issuer/outbox", headers=hb)).json() == []
        event_id = (await c.get("/issuer/outbox", headers=ha)).json()[0]["event_id"]
        assert (await c.post(f"/issuer/outbox/{event_id}/ack", headers=hb)).status_code == 404
        # L'événement n'a pas été acquitté par le tenant B.
        assert len((await c.get("/issuer/outbox", headers=ha)).json()) == 1
        assert (await c.get("/issuer/outbox")).status_code == 401


@pytestmark_db
async def test_manual_transport_leaves_sms_pending_but_sends_email(
    storage: MemoryStorage,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tid, ha = await tenant()
    rid, _ = await accepted_request(storage, tid, ha)
    monkeypatch.setattr(dispatch, "manual_channels", lambda: frozenset({NotificationChannel.sms}))
    t = dispatch.MockTransport()
    await dispatch.dispatch_pending(t)
    assert all(m.channel != NotificationChannel.sms for m in t.sent)
    async with tenant_session(tid) as s:
        rows = await s.scalars(
            select(NotificationEvent).where(
                NotificationEvent.document_request_id == rid,
                NotificationEvent.event_type == "processing_started",
            )
        )
        got = {e.channel: e.send_status for e in rows}
    assert got[NotificationChannel.sms] == NotificationSendStatus.pending
    assert got[NotificationChannel.email] == NotificationSendStatus.sent
