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


async def notify(
    session: AsyncSession,
    *,
    request_id: uuid.UUID,
    user_id: uuid.UUID,
    event_type: EventType,
    channels: tuple[NotificationChannel, ...],
) -> None:
    key = f"{request_id}:{event_type}"
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
