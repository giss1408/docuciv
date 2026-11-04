"""Envoi des notifications `pending` (docs/notifications.md §1, §7).

Transport simulé pour l'instant: rien n'est réellement envoyé. Les fournisseurs SMS/email/push
(NEXT_STEPS §4) viendront remplacer `MockTransport` derrière le même Protocol.

Le contenu des messages n'est ni généré ni stocké ici (PII, §7): le transport reçoit uniquement
des identifiants techniques.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Protocol

import structlog
from sqlalchemy import text

from app.db import get_engine
from app.models import NotificationChannel

log = structlog.get_logger()

BATCH_SIZE = 100


@dataclass(frozen=True)
class Outgoing:
    event_id: str
    user_id: str | None
    request_id: str | None
    event_type: str
    channel: NotificationChannel


class Transport(Protocol):
    async def send(self, message: Outgoing) -> None:
        """Lève une exception si l'envoi échoue (la notification passe alors en `failed`)."""
        ...


@dataclass
class MockTransport:
    """Enregistre les envois en mémoire. `fail_for` simule une panne par canal."""

    sent: list[Outgoing] = field(default_factory=list)
    fail_for: set[NotificationChannel] = field(default_factory=set)

    async def send(self, message: Outgoing) -> None:
        if message.channel in self.fail_for:
            raise ConnectionError(f"mock {message.channel} unavailable")
        self.sent.append(message)
        log.info(
            "notification_mock_sent",
            event_id=message.event_id,
            event_type=message.event_type,
            channel=message.channel,
        )


def get_transport() -> Transport:
    return MockTransport()


async def dispatch_pending(transport: Transport | None = None) -> dict[str, int]:
    transport = transport or get_transport()
    counts = {"sent": 0, "failed": 0, "skipped": 0}
    async with get_engine().connect() as conn:
        rows = (
            await conn.execute(
                text("SELECT * FROM docuciv_pending_notifications(:n)"), {"n": BATCH_SIZE}
            )
        ).all()
        await conn.commit()

        async def cas(event_id: object, expected: str, new: str) -> bool:
            ok = await conn.scalar(
                text("SELECT docuciv_set_notification_status(:i, :e, :n)"),
                {"i": event_id, "e": expected, "n": new},
            )
            await conn.commit()
            return bool(ok)

        for row in rows:
            # Prendre la main avant d'envoyer: un autre worker concurrent n'envoie pas deux fois.
            if not await cas(row.id, "pending", "sent"):
                counts["skipped"] += 1
                continue
            message = Outgoing(
                event_id=str(row.id),
                user_id=str(row.user_id) if row.user_id else None,
                request_id=str(row.document_request_id) if row.document_request_id else None,
                event_type=row.event_type,
                channel=NotificationChannel(row.channel),
            )
            try:
                # in_app: rien à pousser, la notification est consultable dans l'application.
                if message.channel != NotificationChannel.in_app:
                    await transport.send(message)
                counts["sent"] += 1
            except Exception:
                log.warning("notification_send_failed", event_id=message.event_id)
                await cas(row.id, "sent", "failed")
                counts["failed"] += 1
    log.info("notifications_dispatched", **counts)
    return counts


if __name__ == "__main__":
    asyncio.run(dispatch_pending())
