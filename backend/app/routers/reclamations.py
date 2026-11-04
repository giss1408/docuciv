import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.auth import Principal, get_principal
from app.config import Settings, get_settings
from app.db import user_session
from app.models import (
    DocumentRequest,
    NotificationChannel,
    Reclamation,
    ReclamationCategory,
    ReclamationStatus,
    User,
)
from app.services.notifications import EventType, notify

router = APIRouter(prefix="/reclamations", tags=["reclamations"])
log = structlog.get_logger()

# SLA de réponse (notifications.md §6, Priorisation): plus court pour paiement et fraude.
_PRIORITY = {ReclamationCategory.payment_issue, ReclamationCategory.fraud_suspicion}
_SLA_PRIORITY = timedelta(hours=24)
_SLA_DEFAULT = timedelta(hours=48)


def sla_due(category: ReclamationCategory, now: datetime) -> datetime:
    return now + (_SLA_PRIORITY if category in _PRIORITY else _SLA_DEFAULT)


class CreateReclamationIn(BaseModel):
    document_request_id: uuid.UUID | None = None
    category: ReclamationCategory
    description: str = Field(max_length=2000)

    @field_validator("description")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            raise ValueError("description too short")
        return v


class ReclamationOut(BaseModel):
    id: uuid.UUID
    document_request_id: uuid.UUID | None
    category: ReclamationCategory
    description: str
    status: ReclamationStatus
    sla_response_due_at: datetime
    response: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, r: Reclamation) -> "ReclamationOut":
        return cls(
            id=r.id,
            document_request_id=r.document_request_id,
            category=r.category,
            description=r.description,
            status=r.status,
            sla_response_due_at=r.sla_response_due_at,
            response=r.response,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )


class CreateReclamationOut(BaseModel):
    id: uuid.UUID
    status: ReclamationStatus
    sla_response_due_at: datetime


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CreateReclamationOut)
async def create_reclamation(
    body: CreateReclamationIn,
    principal: Annotated[Principal, Depends(get_principal)],
) -> CreateReclamationOut:
    now = datetime.now(UTC)
    async with user_session(principal.user_id) as session:
        if await session.get(User, principal.user_id) is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication_required")
        tenant_id: uuid.UUID | None = None
        if body.document_request_id is not None:
            request = await session.get(DocumentRequest, body.document_request_id)
            # RLS: la demande d'un autre citoyen est invisible -> même 404 qu'une demande inconnue.
            if request is None or request.user_id != principal.user_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "request_not_found")
            tenant_id = request.administration_id
        reclamation = Reclamation(
            user_id=principal.user_id,
            tenant_id=tenant_id,
            document_request_id=body.document_request_id,
            category=body.category,
            description=body.description,
            status=ReclamationStatus.open,
            sla_response_due_at=sla_due(body.category, now),
        )
        session.add(reclamation)
        await session.flush()
        await notify(
            session,
            request_id=body.document_request_id,
            user_id=principal.user_id,
            event_type=EventType.reclamation_received,
            channels=(NotificationChannel.email, NotificationChannel.sms),
            discriminator=reclamation.id,
        )
        out = CreateReclamationOut(
            id=reclamation.id,
            status=reclamation.status,
            sla_response_due_at=reclamation.sla_response_due_at,
        )
    log.info("reclamation_created", reclamation_id=str(out.id), category=body.category)
    return out


@router.get("", response_model=list[ReclamationOut])
async def list_reclamations(
    principal: Annotated[Principal, Depends(get_principal)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ReclamationOut]:
    async with user_session(principal.user_id) as session:
        rows = await session.scalars(
            select(Reclamation)
            .where(Reclamation.user_id == principal.user_id)  # en plus de la RLS
            .order_by(Reclamation.created_at.desc(), Reclamation.id)
            .limit(limit)
            .offset(offset)
        )
        return [ReclamationOut.of(r) for r in rows]


@router.post("/{reclamation_id}/reopen", response_model=ReclamationOut)
async def reopen_reclamation(
    reclamation_id: uuid.UUID,
    principal: Annotated[Principal, Depends(get_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReclamationOut:
    now = datetime.now(UTC)
    async with user_session(principal.user_id) as session:
        r = await session.scalar(
            select(Reclamation)
            .where(Reclamation.id == reclamation_id, Reclamation.user_id == principal.user_id)
            .with_for_update()
        )
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "reclamation_not_found")
        if r.status not in (ReclamationStatus.resolved, ReclamationStatus.rejected):
            raise HTTPException(status.HTTP_409_CONFLICT, "not_reopenable")
        if now - r.updated_at > timedelta(days=settings.reclamation_reopen_days):
            raise HTTPException(status.HTTP_409_CONFLICT, "reopen_window_expired")
        r.status = ReclamationStatus.reopened
        r.sla_response_due_at = sla_due(r.category, now)
        r.updated_at = now
        await session.flush()
        return ReclamationOut.of(r)
