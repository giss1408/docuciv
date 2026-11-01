"""Smoke tests du contrôle d'existence avant paiement (notifications.md §3, roadmap Phase 2)."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db import tenant_session, user_session
from app.main import app
from app.models import (
    Administration,
    AdministrationRole,
    DocumentRequest,
    DocumentRequestStatusHistory,
    NotificationChannel,
    NotificationEvent,
    NotificationSendStatus,
    ReferenceCheckResult,
    RequestStatus,
    User,
    UserType,
)
from app.services.notifications import EventType, notify
from app.services.reference_check import get_reference_checker, run_reference_check
from app.services.state_machine import InvalidTransitionError, transition

pytestmark = pytest.mark.usefixtures("migrated_db")

BODY = {"document_type": "acte_naissance", "reference_document_id": "AN-1998-004512"}


class Fake:
    def __init__(self, result: ReferenceCheckResult | None = None) -> None:
        self.result, self.calls = result, 0

    async def check(self, *_: object) -> ReferenceCheckResult:
        self.calls += 1
        if self.result is None:
            raise TimeoutError
        return self.result


@pytest.fixture(autouse=True)
def _clear_overrides():  # type: ignore[no-untyped-def]
    yield
    app.dependency_overrides.clear()


async def _create(checker: Fake) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    app.dependency_overrides[get_reference_checker] = lambda: checker
    tid, uid = uuid.uuid4(), uuid.uuid4()
    async with tenant_session(tid) as s:
        s.add(Administration(id=tid, name="Mairie", role=AdministrationRole.issuer))
    async with user_session(uid) as s:
        s.add(User(id=uid, type=UserType.citizen, full_name="Awa", phone="+2250100000000"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(
            "/requests",
            json={**BODY, "administration_id": str(tid)},
            headers={"X-Dev-User-Id": str(uid)},
        )
    assert r.status_code == 201
    assert r.json()["status"] == "pending_reference_check"  # réponse avant le contrôle
    return uuid.UUID(r.json()["id"]), tid, uid


async def _state(rid: uuid.UUID, uid: uuid.UUID):  # type: ignore[no-untyped-def]
    async with user_session(uid) as s:
        req = await s.get(DocumentRequest, rid)
        assert req is not None
        history = (
            await s.scalars(
                select(DocumentRequestStatusHistory)
                .where(DocumentRequestStatusHistory.document_request_id == rid)
                .order_by(DocumentRequestStatusHistory.changed_at)
            )
        ).all()
        events = (
            await s.scalars(
                select(NotificationEvent).where(NotificationEvent.document_request_id == rid)
            )
        ).all()
    return req, history, {(e.event_type, e.channel) for e in events}


@pytest.mark.parametrize(
    ("result", "status", "event", "channels"),
    [
        (
            ReferenceCheckResult.found,
            RequestStatus.pending_payment,
            "reference_found",
            {NotificationChannel.in_app},
        ),
        (
            ReferenceCheckResult.not_found,
            RequestStatus.reference_not_found,
            "reference_not_found",
            {NotificationChannel.email, NotificationChannel.sms},
        ),
        (
            ReferenceCheckResult.unverifiable,
            RequestStatus.pending_payment,
            "reference_unverifiable",
            {NotificationChannel.in_app},
        ),
    ],
)
async def test_outcomes_transition_and_notify(
    result: ReferenceCheckResult,
    status: RequestStatus,
    event: str,
    channels: set[NotificationChannel],
) -> None:
    rid, _, uid = await _create(Fake(result))
    req, history, events = await _state(rid, uid)
    assert req.status == status and req.reference_check == result
    assert [h.to_status for h in history] == [RequestStatus.pending_reference_check, status]
    assert history[1].from_status == RequestStatus.pending_reference_check
    assert events == {("request_created", NotificationChannel.in_app)} | {
        (event, c) for c in channels
    }


async def test_checker_error_keeps_pending_and_never_opens_payment() -> None:
    rid, _, uid = await _create(Fake(None))
    req, history, events = await _state(rid, uid)
    assert req.status == RequestStatus.pending_reference_check and req.reference_check is None
    assert len(history) == 1
    assert {e for e, _ in events} == {"request_created"}


async def test_rerun_is_idempotent() -> None:
    checker = Fake(ReferenceCheckResult.found)
    rid, tid, uid = await _create(checker)
    await run_reference_check(rid, tid, checker)
    _, history, events = await _state(rid, uid)
    assert len(history) == 2 and checker.calls == 1  # pas même rappelé: statut déjà quitté
    assert len(events) == 2


async def test_notify_duplicate_is_skipped_not_resent() -> None:
    rid, tid, uid = await _create(Fake(None))
    async with tenant_session(tid) as s:
        for _ in range(2):
            await notify(
                s,
                request_id=rid,
                user_id=uid,
                event_type=EventType.reference_found,
                channels=(NotificationChannel.in_app,),
            )
        rows = (
            await s.scalars(
                select(NotificationEvent).where(
                    NotificationEvent.idempotency_key == f"{rid}:reference_found"
                )
            )
        ).all()
    assert sorted(r.send_status for r in rows) == [
        NotificationSendStatus.pending,
        NotificationSendStatus.skipped_duplicate,
    ]


async def test_state_machine_rejects_illegal_transition() -> None:
    rid, tid, _ = await _create(Fake(None))
    async with tenant_session(tid) as s:
        with pytest.raises(InvalidTransitionError):
            await transition(s, rid, RequestStatus.pending_reference_check, RequestStatus.issued)
        # statut courant différent de celui attendu: no-op
        assert await transition(s, rid, RequestStatus.pending_payment, RequestStatus.paid) is None


async def test_other_tenant_cannot_run_check_on_foreign_request() -> None:
    rid, _, uid = await _create(Fake(None))
    other = uuid.uuid4()
    async with tenant_session(other) as s:
        s.add(Administration(id=other, name="Autre", role=AdministrationRole.issuer))
    checker = Fake(ReferenceCheckResult.not_found)
    await run_reference_check(rid, other, checker)
    req, history, _ = await _state(rid, uid)
    assert req.status == RequestStatus.pending_reference_check and checker.calls == 0
    assert len(history) == 1
