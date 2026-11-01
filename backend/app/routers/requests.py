import json
import re
import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from app.auth import Principal, get_principal
from app.config import Settings, get_settings
from app.db import user_session
from app.models import (
    DocumentRequest,
    DocumentRequestStatusHistory,
    DocumentType,
    RequestStatus,
    User,
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
        request_id = request.id

    # Pas de PII dans les logs: identifiants techniques uniquement.
    log.info("request_created", request_id=str(request_id), document_type=body.document_type)
    return CreateRequestOut(
        id=request_id,
        status=RequestStatus.pending_reference_check,
        amount_due=settings.default_amount_due_fcfa,
    )
