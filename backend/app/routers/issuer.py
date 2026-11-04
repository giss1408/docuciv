import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AgentPrincipal, get_issuer_agent
from app.config import Settings, get_settings
from app.db import tenant_session
from app.models import (
    DocumentRequest,
    DocumentType,
    NotificationChannel,
    Reclamation,
    ReclamationCategory,
    ReclamationStatus,
    ReferenceCheckResult,
    RequestStatus,
    ReviewStatus,
    SourceEvidence,
    UploadStatus,
)
from app.routers.reclamations import ReclamationOut
from app.services.notifications import EventType, notify
from app.services.review import estimate_ready_at
from app.services.state_machine import transition
from app.services.storage import ObjectStorage, get_storage

router = APIRouter(prefix="/issuer", tags=["issuer"])
log = structlog.get_logger()

_QUEUE_STATUSES = (RequestStatus.in_review, RequestStatus.in_progress, RequestStatus.paid)


class QueueItem(BaseModel):
    id: uuid.UUID
    status: RequestStatus
    document_type: DocumentType
    reference_document_id: str
    # `unverifiable`: l'agent doit vérifier lui-même l'existence du document de référence.
    reference_check: ReferenceCheckResult | None
    created_at: datetime
    # Posé par le job de relance quand le délai estimé a été dépassé (file de relance).
    overdue_notified_at: datetime | None


class EvidenceView(BaseModel):
    evidence_id: uuid.UUID
    mime_type: str
    review_status: ReviewStatus | None
    view_url: str
    expires_in: int


class ReviewIn(BaseModel):
    decision: Literal["accepted", "rejected"]
    review_notes: str | None = Field(default=None, max_length=500)


class ReviewOut(BaseModel):
    request_status: RequestStatus
    estimated_ready_at: datetime | None


@router.get("/requests", response_model=list[QueueItem])
async def list_requests(
    agent: Annotated[AgentPrincipal, Depends(get_issuer_agent)],
    status_filter: Annotated[RequestStatus | None, Query(alias="status")] = None,
    overdue: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[QueueItem]:
    if status_filter is None:
        status_filter = RequestStatus.in_progress if overdue else RequestStatus.in_review
    if status_filter not in _QUEUE_STATUSES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "status_not_listable")
    conditions = [
        DocumentRequest.administration_id == agent.tenant_id,  # en plus de la RLS
        DocumentRequest.status == status_filter,
    ]
    if overdue:
        conditions.append(DocumentRequest.overdue_notified_at.is_not(None))
    async with tenant_session(agent.tenant_id) as session:
        rows = await session.scalars(
            select(DocumentRequest)
            .where(*conditions)
            .order_by(DocumentRequest.created_at, DocumentRequest.id)
            .limit(limit)
            .offset(offset)
        )
        return [
            QueueItem(
                id=r.id,
                status=r.status,
                document_type=r.document_type,
                reference_document_id=r.reference_document_id,
                reference_check=r.reference_check,
                created_at=r.created_at,
                overdue_notified_at=r.overdue_notified_at,
            )
            for r in rows
        ]


async def _own_request(
    session: AsyncSession, request_id: uuid.UUID, agent: AgentPrincipal
) -> DocumentRequest:
    request = await session.get(DocumentRequest, request_id)
    if request is None or request.administration_id != agent.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "request_not_found")
    return request


@router.get("/requests/{request_id}/evidence", response_model=list[EvidenceView])
async def view_evidence(
    request_id: uuid.UUID,
    agent: Annotated[AgentPrincipal, Depends(get_issuer_agent)],
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[ObjectStorage, Depends(get_storage)],
) -> list[EvidenceView]:
    async with tenant_session(agent.tenant_id) as session:
        await _own_request(session, request_id, agent)
        evidence = (
            await session.scalars(
                select(SourceEvidence)
                .where(
                    SourceEvidence.document_request_id == request_id,
                    SourceEvidence.upload_status == UploadStatus.validated,
                )
                .order_by(SourceEvidence.created_at)
            )
        ).all()
    # URLs signées de courte durée; jamais d'accès S3 direct ni permanent (security.md §2bis).
    views = [
        EvidenceView(
            evidence_id=e.id,
            mime_type=e.mime_type or "",
            review_status=e.review_status,
            view_url=await storage.presign_download(
                e.file_storage_key, settings.evidence_view_ttl_seconds
            ),
            expires_in=settings.evidence_view_ttl_seconds,
        )
        for e in evidence
    ]
    log.info("evidence_viewed", request_id=str(request_id), agent_id=str(agent.agent_id))
    return views


@router.post("/requests/{request_id}/evidence/{evidence_id}/review", response_model=ReviewOut)
async def review_evidence(
    request_id: uuid.UUID,
    evidence_id: uuid.UUID,
    body: ReviewIn,
    agent: Annotated[AgentPrincipal, Depends(get_issuer_agent)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReviewOut:
    notes = (body.review_notes or "").strip()
    if body.decision == "rejected" and not notes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "review_notes_required")

    async with tenant_session(agent.tenant_id) as session:
        request = await _own_request(session, request_id, agent)
        evidence = await session.get(SourceEvidence, evidence_id)
        if evidence is None or evidence.document_request_id != request_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "evidence_not_found")
        if (
            request.status != RequestStatus.in_review
            or evidence.upload_status != UploadStatus.validated
            or evidence.review_status != ReviewStatus.pending
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "not_reviewable")

        accepted = body.decision == "accepted"
        estimated: datetime | None = None
        to = RequestStatus.in_progress if accepted else RequestStatus.rejected
        moved = await transition(
            session,
            request_id,
            RequestStatus.in_review,
            to,
            reason=None if accepted else notes,
        )
        if moved is None:  # un autre agent a statué entre-temps
            raise HTTPException(status.HTTP_409_CONFLICT, "not_reviewable")

        evidence.reviewed_by = agent.agent_id
        evidence.review_status = ReviewStatus.accepted if accepted else ReviewStatus.rejected
        evidence.review_notes = notes or None
        if accepted:
            estimated = await estimate_ready_at(
                session, request.administration_id, request.document_type, settings
            )
            moved.estimated_ready_at = estimated
        else:
            moved.rejection_reason = notes

        await notify(
            session,
            request_id=request_id,
            user_id=request.user_id,
            event_type=EventType.processing_started
            if accepted
            else EventType.evidence_rejected_review,
            channels=(NotificationChannel.email, NotificationChannel.sms),
        )
        result = ReviewOut(request_status=to, estimated_ready_at=estimated)

    log.info(
        "evidence_reviewed",
        request_id=str(request_id),
        decision=body.decision,
        agent_id=str(agent.agent_id),
    )
    return result


_OPEN_RECLAMATIONS = (
    ReclamationStatus.open,
    ReclamationStatus.in_progress,
    ReclamationStatus.reopened,
)


class IssuerReclamation(ReclamationOut):
    handled_by: uuid.UUID | None


class RespondIn(BaseModel):
    status: Literal["resolved", "rejected"]
    response: str = Field(min_length=1, max_length=2000)


@router.get("/reclamations", response_model=list[IssuerReclamation])
async def list_reclamations(
    agent: Annotated[AgentPrincipal, Depends(get_issuer_agent)],
    status_filter: Annotated[ReclamationStatus | None, Query(alias="status")] = None,
    category: ReclamationCategory | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[IssuerReclamation]:
    """File des réclamations du tenant, les plus proches de leur SLA d'abord."""
    conditions = [Reclamation.tenant_id == agent.tenant_id]  # en plus de la RLS
    conditions.append(
        Reclamation.status == status_filter
        if status_filter
        else Reclamation.status.in_(_OPEN_RECLAMATIONS)
    )
    if category:
        conditions.append(Reclamation.category == category)
    async with tenant_session(agent.tenant_id) as session:
        rows = await session.scalars(
            select(Reclamation)
            .where(*conditions)
            .order_by(Reclamation.sla_response_due_at, Reclamation.id)
            .limit(limit)
            .offset(offset)
        )
        return [
            IssuerReclamation(**ReclamationOut.of(r).model_dump(), handled_by=r.handled_by)
            for r in rows
        ]


@router.post("/reclamations/{reclamation_id}/respond", response_model=IssuerReclamation)
async def respond_to_reclamation(
    reclamation_id: uuid.UUID,
    body: RespondIn,
    agent: Annotated[AgentPrincipal, Depends(get_issuer_agent)],
) -> IssuerReclamation:
    async with tenant_session(agent.tenant_id) as session:
        r = await session.scalar(
            select(Reclamation)
            .where(Reclamation.id == reclamation_id, Reclamation.tenant_id == agent.tenant_id)
            .with_for_update()
        )
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "reclamation_not_found")
        if r.status not in _OPEN_RECLAMATIONS:  # déjà répondue (ex. par un autre agent)
            raise HTTPException(status.HTTP_409_CONFLICT, "already_answered")
        r.status = ReclamationStatus(body.status)
        r.response = body.response.strip()
        r.handled_by = agent.agent_id
        # Explicite: l'onupdate serveur expirerait l'attribut, non relisible hors greenlet.
        r.updated_at = datetime.now(UTC)
        await session.flush()
        await notify(
            session,
            request_id=r.document_request_id,
            user_id=r.user_id,
            event_type=EventType.reclamation_answered,
            channels=(NotificationChannel.email, NotificationChannel.sms),
            # Une réclamation rouverte peut recevoir plusieurs réponses, chacune notifiée.
            discriminator=uuid.uuid4(),
        )
        out = IssuerReclamation(**ReclamationOut.of(r).model_dump(), handled_by=r.handled_by)
    log.info(
        "reclamation_answered",
        reclamation_id=str(reclamation_id),
        status=body.status,
        agent_id=str(agent.agent_id),
    )
    return out
