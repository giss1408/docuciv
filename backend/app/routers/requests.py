import json
import re
import uuid
from datetime import datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text

from app.auth import Principal, get_principal
from app.config import Settings, get_settings
from app.db import user_session
from app.models import (
    DocumentRequest,
    DocumentRequestStatusHistory,
    DocumentType,
    NotificationChannel,
    RequestStatus,
    ReviewStatus,
    SourceEvidence,
    UploadStatus,
    User,
)
from app.services.notifications import EventType, notify
from app.services.reference_check import (
    ReferenceChecker,
    get_reference_checker,
    run_reference_check,
)

router = APIRouter(prefix="/requests", tags=["requests"])
log = structlog.get_logger()

_REFERENCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-/_.]{2,63}$")
_MAX_PAYLOAD_BYTES = 16_384


class CreateRequestIn(BaseModel):
    administration_id: uuid.UUID
    document_type: DocumentType
    reference_document_id: str
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reference_document_id")
    @classmethod
    def _valid_reference(cls, v: str) -> str:
        v = v.strip()
        if not _REFERENCE_RE.match(v):
            raise ValueError("invalid reference_document_id")
        return v

    @field_validator("payload")
    @classmethod
    def _bounded_payload(cls, v: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(v).encode()) > _MAX_PAYLOAD_BYTES:
            raise ValueError("payload too large")
        return v


class CreateRequestOut(BaseModel):
    id: uuid.UUID
    status: RequestStatus
    amount_due: int


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CreateRequestOut)
async def create_request(
    body: CreateRequestIn,
    background: BackgroundTasks,
    checker: Annotated[ReferenceChecker, Depends(get_reference_checker)],
    principal: Annotated[Principal, Depends(get_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CreateRequestOut:
    async with user_session(principal.user_id) as session:
        if await session.get(User, principal.user_id) is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication_required")

        accepted = await session.scalar(
            text("SELECT issuer_accepts_requests(:id)"), {"id": body.administration_id}
        )
        if not accepted:
            # Même réponse pour inexistante / suspendue / non émettrice: pas d'énumération.
            raise HTTPException(status.HTTP_404_NOT_FOUND, "administration_unavailable")

        request = DocumentRequest(
            user_id=principal.user_id,
            administration_id=body.administration_id,
            document_type=body.document_type,
            reference_document_id=body.reference_document_id,
            status=RequestStatus.pending_reference_check,
            payload=body.payload,
        )
        session.add(request)
        await session.flush()
        session.add(
            DocumentRequestStatusHistory(
                document_request_id=request.id,
                from_status=None,
                to_status=RequestStatus.pending_reference_check,
            )
        )
        await notify(
            session,
            request_id=request.id,
            user_id=principal.user_id,
            event_type=EventType.request_created,
            channels=(NotificationChannel.in_app,),
        )
        request_id = request.id

    # Après la réponse: la demande est renvoyée en pending_reference_check (api-spec.md), le
    # contrôle la fait ensuite passer à pending_payment ou reference_not_found.
    background.add_task(run_reference_check, request_id, body.administration_id, checker)

    # Pas de PII dans les logs: identifiants techniques uniquement.
    log.info("request_created", request_id=str(request_id), document_type=body.document_type)
    return CreateRequestOut(
        id=request_id,
        status=RequestStatus.pending_reference_check,
        amount_due=settings.default_amount_due_fcfa,
    )


class HistoryItem(BaseModel):
    # Pas de `reason`: il peut porter des notes internes (voir rejection_reason pour le citoyen).
    to_status: RequestStatus
    changed_at: datetime


class RequestDetail(BaseModel):
    id: uuid.UUID
    status: RequestStatus
    document_type: DocumentType
    reference_document_id: str
    evidence_review_status: ReviewStatus | None
    rejection_reason: str | None
    estimated_ready_at: datetime | None
    created_at: datetime
    history: list[HistoryItem]


class RequestSummary(BaseModel):
    id: uuid.UUID
    status: RequestStatus
    document_type: DocumentType
    reference_document_id: str
    estimated_ready_at: datetime | None
    created_at: datetime
    updated_at: datetime


@router.get("", response_model=list[RequestSummary])
async def list_requests(
    principal: Annotated[Principal, Depends(get_principal)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RequestSummary]:
    """« Mes démarches »: les demandes du citoyen authentifié, plus récentes d'abord."""
    async with user_session(principal.user_id) as session:
        rows = await session.scalars(
            select(DocumentRequest)
            .where(DocumentRequest.user_id == principal.user_id)  # en plus de la RLS
            .order_by(DocumentRequest.created_at.desc(), DocumentRequest.id)
            .limit(limit)
            .offset(offset)
        )
        return [RequestSummary.model_validate(r, from_attributes=True) for r in rows]


@router.get("/{request_id}", response_model=RequestDetail)
async def get_request(
    request_id: uuid.UUID,
    principal: Annotated[Principal, Depends(get_principal)],
) -> RequestDetail:
    async with user_session(principal.user_id) as session:
        request = await session.get(DocumentRequest, request_id)
        # Demande d'un autre citoyen: invisible par RLS -> 404, sans révéler son existence.
        if request is None or request.user_id != principal.user_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "request_not_found")
        history = await session.scalars(
            select(DocumentRequestStatusHistory)
            .where(DocumentRequestStatusHistory.document_request_id == request_id)
            .order_by(DocumentRequestStatusHistory.changed_at)
        )
        # Pièce la plus récente passée la validation technique (les uploads échoués n'ont pas
        # de review_status).
        review_status = await session.scalar(
            select(SourceEvidence.review_status)
            .where(
                SourceEvidence.document_request_id == request_id,
                SourceEvidence.upload_status == UploadStatus.validated,
            )
            .order_by(SourceEvidence.uploaded_at.desc())
            .limit(1)
        )
        return RequestDetail(
            id=request.id,
            status=request.status,
            document_type=request.document_type,
            reference_document_id=request.reference_document_id,
            evidence_review_status=review_status,
            rejection_reason=request.rejection_reason,
            estimated_ready_at=request.estimated_ready_at,
            created_at=request.created_at,
            history=[HistoryItem(to_status=h.to_status, changed_at=h.changed_at) for h in history],
        )
