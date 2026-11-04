"""Outbox de l'Admin Portal: messages SMS « à envoyer » que l'agent transmet par WhatsApp.

Le backend rend le message et construit le lien `wa.me` prérempli; l'agent l'ouvre et envoie
lui-même (aucune API WhatsApp, aucune donnée confiée à un tiers par le backend). Le texte n'est
pas stocké: il est rendu à la demande (docs/notifications.md §7).
"""

import uuid
from datetime import datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, text

from app.auth import AgentPrincipal, get_issuer_agent
from app.db import tenant_session
from app.models import (
    Administration,
    DocumentRequest,
    NotificationChannel,
    NotificationEvent,
    NotificationSendStatus,
)
from app.services.messages import MessageContext, render_message, whatsapp_url

router = APIRouter(prefix="/issuer/outbox", tags=["outbox"])
log = structlog.get_logger()


class OutboxItem(BaseModel):
    event_id: uuid.UUID
    request_id: uuid.UUID
    event_type: str
    to_send: bool
    message: str
    # Lien wa.me prérempli; null si le numéro du citoyen est inexploitable.
    whatsapp_url: str | None
    created_at: datetime


@router.get("", response_model=list[OutboxItem])
async def list_outbox(
    agent: Annotated[AgentPrincipal, Depends(get_issuer_agent)],
    pending_only: bool = True,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[OutboxItem]:
    conditions = [
        NotificationEvent.channel == NotificationChannel.sms,
        DocumentRequest.administration_id == agent.tenant_id,  # en plus de la RLS
    ]
    if pending_only:
        conditions.append(NotificationEvent.send_status == NotificationSendStatus.pending)
    else:
        conditions.append(
            NotificationEvent.send_status.in_(
                (NotificationSendStatus.pending, NotificationSendStatus.sent)
            )
        )
    async with tenant_session(agent.tenant_id) as session:
        tenant = await session.get(Administration, agent.tenant_id)
        assert tenant is not None  # garanti par get_issuer_agent
        rows = (
            await session.execute(
                select(NotificationEvent, DocumentRequest)
                .join(DocumentRequest, DocumentRequest.id == NotificationEvent.document_request_id)
                .where(*conditions)
                .order_by(NotificationEvent.created_at, NotificationEvent.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        items: list[OutboxItem] = []
        for event, request in rows:
            message = render_message(
                event.event_type,
                MessageContext(
                    request_id=request.id,
                    document_type=request.document_type,
                    administration=tenant.name,
                    estimated_ready_at=request.estimated_ready_at,
                    rejection_reason=request.rejection_reason,
                ),
            )
            phone = await session.scalar(
                text("SELECT docuciv_request_phone(:r, :t)"),
                {"r": request.id, "t": agent.tenant_id},
            )
            items.append(
                OutboxItem(
                    event_id=event.id,
                    request_id=request.id,
                    event_type=event.event_type,
                    to_send=event.send_status == NotificationSendStatus.pending,
                    message=message,
                    whatsapp_url=whatsapp_url(phone, message) if phone else None,
                    created_at=event.created_at,
                )
            )
    return items


@router.post("/{event_id}/ack", status_code=status.HTTP_204_NO_CONTENT)
async def acknowledge(
    event_id: uuid.UUID, agent: Annotated[AgentPrincipal, Depends(get_issuer_agent)]
) -> None:
    """L'agent confirme avoir envoyé le message. Idempotent côté client: 409 si déjà acquitté."""
    async with tenant_session(agent.tenant_id) as session:
        ok = await session.scalar(
            text("SELECT docuciv_ack_outbox(:e, :t)"), {"e": event_id, "t": agent.tenant_id}
        )
    if not ok:
        # Inconnu, d'un autre tenant ou déjà acquitté: même réponse, pas d'énumération.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "outbox_item_not_found")
    log.info("outbox_acknowledged", event_id=str(event_id), agent_id=str(agent.agent_id))
