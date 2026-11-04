"""Smoke tests du job de relance (notifications.md §4, roadmap Phase 2)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from helpers import Found
from sqlalchemy import select
from test_issuer import client, tenant

from app.db import tenant_session, user_session
from app.models import (
    DocumentRequest,
    DocumentType,
    NotificationEvent,
    NotificationSendStatus,
    ReferenceCheckResult,
    RequestStatus,
    User,
    UserType,
)
from app.services.followup import run_followups

pytestmark = pytest.mark.usefixtures("migrated_db")

NOW = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)  # un mercredi


async def make_request(
    tid: uuid.UUID,
    status: RequestStatus,
    *,
    estimated: datetime | None = None,
    created: datetime | None = None,
) -> uuid.UUID:
    uid, rid = uuid.uuid4(), uuid.uuid4()
    async with user_session(uid) as s:
        s.add(User(id=uid, type=UserType.citizen, full_name="Awa", phone="+2250100000000"))
    async with tenant_session(tid) as s:
        s.add(
            DocumentRequest(
                id=rid,
                user_id=uid,
                administration_id=tid,
                document_type=DocumentType.acte_naissance,
                reference_document_id="AN-1",
                status=status,
                estimated_ready_at=estimated,
                created_at=created or NOW,
            )
        )
    return rid


async def get(tid: uuid.UUID, rid: uuid.UUID) -> DocumentRequest:
    async with tenant_session(tid) as s:
        req = await s.get(DocumentRequest, rid)
        assert req is not None
        return req


async def overdue_events(tid: uuid.UUID, rid: uuid.UUID) -> list[NotificationEvent]:
    async with tenant_session(tid) as s:
        return list(
            await s.scalars(
                select(NotificationEvent).where(
                    NotificationEvent.document_request_id == rid,
                    NotificationEvent.event_type == "request_overdue",
                )
            )
        )


async def test_overdue_request_is_notified_once_with_new_estimate() -> None:
    tid, _ = await tenant()
    rid = await make_request(tid, RequestStatus.in_progress, estimated=NOW - timedelta(days=1))

    assert (await run_followups(Found(), now=NOW))["overdue"] >= 1
    req = await get(tid, rid)
    assert req.overdue_notified_at == NOW
    assert req.estimated_ready_at is not None and req.estimated_ready_at > NOW
    events = await overdue_events(tid, rid)
    assert {e.channel for e in events} == {"email", "sms"}
    assert all(e.send_status == NotificationSendStatus.pending for e in events)

    # Rejeu: aucune seconde relance ni nouvel événement.
    await run_followups(Found(), now=NOW + timedelta(days=30))
    assert len(await overdue_events(tid, rid)) == len(events)
    assert (await get(tid, rid)).overdue_notified_at == NOW


async def test_not_yet_due_or_other_status_is_untouched() -> None:
    tid, _ = await tenant()
    future = await make_request(tid, RequestStatus.in_progress, estimated=NOW + timedelta(days=2))
    review = await make_request(tid, RequestStatus.in_review, estimated=NOW - timedelta(days=2))
    await run_followups(Found(), now=NOW)
    for rid in (future, review):
        assert (await get(tid, rid)).overdue_notified_at is None
        assert await overdue_events(tid, rid) == []


async def test_stuck_reference_check_is_resumed_but_recent_one_is_not() -> None:
    tid, _ = await tenant()
    stuck = await make_request(
        tid, RequestStatus.pending_reference_check, created=NOW - timedelta(hours=1)
    )
    fresh = await make_request(
        tid, RequestStatus.pending_reference_check, created=NOW - timedelta(minutes=1)
    )
    await run_followups(Found(), now=NOW)
    assert (await get(tid, stuck)).status == RequestStatus.pending_payment
    assert (await get(tid, stuck)).reference_check == ReferenceCheckResult.found
    assert (await get(tid, fresh)).status == RequestStatus.pending_reference_check


async def test_checker_error_leaves_request_stuck_and_does_not_block_others() -> None:
    tid, _ = await tenant()
    stuck = await make_request(
        tid, RequestStatus.pending_reference_check, created=NOW - timedelta(hours=1)
    )
    overdue = await make_request(tid, RequestStatus.in_progress, estimated=NOW - timedelta(days=1))

    class Failing:
        async def check(self, *_: object) -> ReferenceCheckResult:
            raise TimeoutError

    await run_followups(Failing(), now=NOW)
    assert (await get(tid, stuck)).status == RequestStatus.pending_reference_check
    assert (await get(tid, overdue)).overdue_notified_at == NOW


async def test_followup_covers_all_tenants_and_agent_queue_is_isolated() -> None:
    (t1, h1), (t2, h2) = await tenant(), await tenant()
    r1 = await make_request(t1, RequestStatus.in_progress, estimated=NOW - timedelta(days=1))
    r2 = await make_request(t2, RequestStatus.in_progress, estimated=NOW - timedelta(days=1))
    await run_followups(Found(), now=NOW)

    async with client() as c:
        a = await c.get("/issuer/requests?overdue=true", headers=h1)
        b = await c.get("/issuer/requests?overdue=true", headers=h2)
    assert [i["id"] for i in a.json()] == [str(r1)]  # BOLA: jamais la demande de l'autre tenant
    assert [i["id"] for i in b.json()] == [str(r2)]
    assert a.json()[0]["overdue_notified_at"] is not None
