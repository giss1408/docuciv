"""Smoke tests de l'envoi (simulé) des notifications."""

import uuid

import pytest
from helpers import MemoryStorage
from sqlalchemy import select
from test_issuer import citizen_request, client, storage, tenant  # noqa: F401

from app.db import tenant_session
from app.models import NotificationChannel, NotificationEvent, NotificationSendStatus
from app.services.dispatch import MockTransport, dispatch_pending

pytestmark = pytest.mark.usefixtures("migrated_db")


async def statuses(tid: uuid.UUID, rid: uuid.UUID) -> dict[tuple[str, str], str]:
    async with tenant_session(tid) as s:
        rows = await s.scalars(
            select(NotificationEvent).where(NotificationEvent.document_request_id == rid)
        )
        return {(e.event_type, e.channel): e.send_status for e in rows}


async def test_pending_become_sent_once(storage: MemoryStorage) -> None:  # noqa: F811
    tid, _ = await tenant()
    rid, _, h = await citizen_request(storage, tid)
    assert set((await statuses(tid, rid)).values()) == {NotificationSendStatus.pending}

    t = MockTransport()
    first = await dispatch_pending(t)
    assert first["sent"] >= 1 and first["failed"] == 0
    assert set((await statuses(tid, rid)).values()) <= {NotificationSendStatus.sent}
    assert all(m.channel != NotificationChannel.in_app for m in t.sent)  # in_app: rien à pousser

    # Rejeu: rien à renvoyer.
    before = len(t.sent)
    assert (await dispatch_pending(t))["sent"] == 0
    assert len(t.sent) == before


async def test_transport_failure_marks_failed_and_is_not_retried(
    storage: MemoryStorage,  # noqa: F811
) -> None:
    tid, ha = await tenant()
    rid, _, h = await citizen_request(storage, tid)
    async with client() as c:
        r = await c.post(
            "/reclamations",
            json={
                "document_request_id": str(rid),
                "category": "delay",
                "description": "Délai dépassé depuis plusieurs jours.",
            },
            headers=h,
        )
        assert r.status_code == 201
    t = MockTransport(fail_for={NotificationChannel.sms})
    await dispatch_pending(t)
    got = await statuses(tid, rid)
    assert got[("reclamation_received", "sms")] == NotificationSendStatus.failed
    assert got[("reclamation_received", "email")] == NotificationSendStatus.sent
    assert all(m.channel != NotificationChannel.sms for m in t.sent)
    assert (await dispatch_pending(t))["failed"] == 0  # un `failed` n'est pas rejoué


async def test_mock_transport_refused_in_production() -> None:
    from app.config import Settings

    with pytest.raises(ValueError, match="simulé"):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://app:s3cr3t@db.internal:5432/docuciv",
            migration_database_url="postgresql+asyncpg://own:s3cr3t@db.internal:5432/docuciv",
            redis_url="redis://:pw@cache.internal:6379/0",
            s3_secret_access_key="s3cr3t",
            antivirus="clamav",
        )
