"""Job de relance (docs/notifications.md §4), à déclencher quotidiennement (Celery beat).

- `in_progress` dont `estimated_ready_at` est dépassé: nouveau délai, message 10 au citoyen, et
  `overdue_notified_at` posé (une seule relance par demande; sert aussi de file à l'agent).
- `pending_reference_check` bloquée après une erreur du vérificateur: contrôle rejoué.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select, text

from app.config import Settings, get_settings
from app.db import get_engine, tenant_session
from app.models import DocumentRequest, NotificationChannel, RequestStatus
from app.services.notifications import EventType, notify
from app.services.reference_check import (
    ReferenceChecker,
    get_reference_checker,
    run_reference_check,
)
from app.services.review import estimate_ready_at

log = structlog.get_logger()


async def find_followups(stale_before: datetime) -> list[tuple[uuid.UUID, uuid.UUID, str]]:
    """Seule requête inter-tenant: via la fonction SECURITY DEFINER (migration 0006)."""
    async with get_engine().connect() as conn:
        rows = await conn.execute(
            text("SELECT request_id, administration_id, kind FROM docuciv_find_followups(:t)"),
            {"t": stale_before},
        )
        return [(r.request_id, r.administration_id, r.kind) for r in rows]


async def _notify_overdue(
    request_id: uuid.UUID, tenant_id: uuid.UUID, settings: Settings, now: datetime
) -> bool:
    async with tenant_session(tenant_id) as session:
        # Verrou + revalidation: un rejeu concurrent ou une émission entre-temps devient un no-op.
        request = await session.scalar(
            select(DocumentRequest).where(DocumentRequest.id == request_id).with_for_update()
        )
        if (
            request is None
            or request.status != RequestStatus.in_progress
            or request.overdue_notified_at is not None
            or request.estimated_ready_at is None
            or request.estimated_ready_at >= now
        ):
            return False
        request.estimated_ready_at = await estimate_ready_at(
            session, request.administration_id, request.document_type, settings, now
        )
        request.overdue_notified_at = now
        await notify(
            session,
            request_id=request_id,
            user_id=request.user_id,
            event_type=EventType.request_overdue,
            channels=(NotificationChannel.email, NotificationChannel.sms),
        )
    return True


async def run_followups(
    checker: ReferenceChecker | None = None,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    settings = settings or get_settings()
    checker = checker or get_reference_checker()
    now = now or datetime.now(UTC)
    stale_before = now - timedelta(minutes=settings.reference_check_stale_minutes)
    done = {"overdue": 0, "stuck_reference_check": 0}
    for request_id, tenant_id, kind in await find_followups(stale_before):
        try:
            if kind == "overdue":
                done[kind] += await _notify_overdue(request_id, tenant_id, settings, now)
            else:
                await run_reference_check(request_id, tenant_id, checker)
                done[kind] += 1
        except Exception:
            # Une demande en échec ne doit pas empêcher la relance des autres.
            log.exception("followup_failed", request_id=str(request_id), kind=kind)
    log.info("followups_done", **done)
    return done


if __name__ == "__main__":
    asyncio.run(run_followups())
