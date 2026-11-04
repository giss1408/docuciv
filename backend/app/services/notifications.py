"""Enregistrement idempotent des notifications (docs/notifications.md §1-2).

L'envoi réel (email/SMS/push) relève du service Notification (item de roadmap dédié): ici on
trace l'événement en `pending`. Le contenu du message n'est jamais stocké.
"""

import enum
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import NotificationChannel, NotificationEvent, NotificationSendStatus


class EventType(enum.StrEnum):
    request_created = "request_created"  # §2 #1
    reference_not_found = "reference_not_found"  # §2 #2a
    reference_found = "reference_found"  # §2 #2b
    reference_unverifiable = "reference_unverifiable"  # §3, bascule directe avec avertissement
    evidence_upload_failed = "evidence_upload_failed"  # §2 #3a
    evidence_received = "evidence_received"  # §2 #3b
    evidence_rejected_review = "evidence_rejected_review"  # §2 #6a
    processing_started = "processing_started"  # §2 #6b
    request_overdue = "request_overdue"  # §2 #10


async def notify(
    session: AsyncSession,
    *,
    request_id: uuid.UUID,
    user_id: uuid.UUID,
    event_type: EventType,
    channels: tuple[NotificationChannel, ...],
    discriminator: uuid.UUID | None = None,
) -> None:
    """`discriminator` distingue les occurrences légitimes répétées d'un même événement
    (ex. plusieurs uploads échoués d'une même demande, chacun doit être notifié)."""
    key = f"{request_id}:{event_type}" + (f":{discriminator}" if discriminator else "")
    for channel in channels:
        inserted = await session.scalar(
            insert(NotificationEvent)
            .values(
                id=uuid.uuid4(),
                document_request_id=request_id,
                user_id=user_id,
                event_type=event_type,
                channel=channel,
                send_status=NotificationSendStatus.pending,
                idempotency_key=key,
            )
            .on_conflict_do_nothing()
            .returning(NotificationEvent.id)
        )
        if inserted is None:
            session.add(
                NotificationEvent(
                    document_request_id=request_id,
                    user_id=user_id,
                    event_type=event_type,
                    channel=channel,
                    send_status=NotificationSendStatus.skipped_duplicate,
                    idempotency_key=key,
                )
            )


async def events_for(session: AsyncSession, request_id: uuid.UUID) -> list[NotificationEvent]:
    return list(
        await session.scalars(
            select(NotificationEvent)
            .where(NotificationEvent.document_request_id == request_id)
            .order_by(NotificationEvent.created_at, NotificationEvent.id)
        )
    )
