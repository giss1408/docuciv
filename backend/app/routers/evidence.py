import asyncio
import uuid
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.auth import Principal, get_principal
from app.config import Settings, get_settings
from app.db import user_session
from app.models import (
    DocumentRequest,
    NotificationChannel,
    RequestStatus,
    ReviewStatus,
    SourceEvidence,
    UploadStatus,
)
from app.services.antivirus import Scanner, ScanUnavailableError, get_scanner
from app.services.evidence import ALLOWED_MIME, EvidenceRejectedError, sanitize
from app.services.notifications import EventType, notify
from app.services.storage import ObjectStorage, get_storage

router = APIRouter(prefix="/requests/{request_id}/evidence", tags=["evidence"])
log = structlog.get_logger()

# Après le contrôle d'existence et avant l'instruction: le citoyen peut joindre sa photo avant
# ou après le paiement (notifications.md §2).
_UPLOADABLE = (RequestStatus.pending_payment, RequestStatus.paid)


class UploadUrlIn(BaseModel):
    mime_type: str
    file_size_bytes: int = Field(gt=0)


class UploadUrlOut(BaseModel):
    evidence_id: uuid.UUID
    upload_url: str
    upload_fields: dict[str, str]
    expires_in: int


class CompleteOut(BaseModel):
    evidence_id: uuid.UUID
    content_hash: str
    review_status: ReviewStatus


def _raw_key(request: DocumentRequest, evidence_id: uuid.UUID) -> str:
    return f"evidence/{request.administration_id}/{request.id}/{evidence_id}/raw"


def _clean_key(request: DocumentRequest, evidence_id: uuid.UUID) -> str:
    return f"evidence/{request.administration_id}/{request.id}/{evidence_id}/clean"


@router.post("/upload-url", status_code=status.HTTP_201_CREATED, response_model=UploadUrlOut)
async def create_upload_url(
    request_id: uuid.UUID,
    body: UploadUrlIn,
    principal: Annotated[Principal, Depends(get_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[ObjectStorage, Depends(get_storage)],
) -> UploadUrlOut:
    if body.mime_type not in ALLOWED_MIME:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unsupported_mime_type")
    if body.file_size_bytes > settings.evidence_max_bytes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "file_too_large")

    async with user_session(principal.user_id) as session:
        # RLS: la demande d'un autre citoyen est invisible -> 404 (pas de fuite d'existence).
        request = await session.get(DocumentRequest, request_id)
        if request is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "request_not_found")
        if request.status not in _UPLOADABLE:
            raise HTTPException(status.HTTP_409_CONFLICT, "request_not_accepting_evidence")
        count = await session.scalar(
            select(func.count())
            .select_from(SourceEvidence)
            .where(SourceEvidence.document_request_id == request_id)
        )
        if (count or 0) >= settings.evidence_max_per_request:
            raise HTTPException(status.HTTP_409_CONFLICT, "too_many_evidence_files")

        evidence = SourceEvidence(
            id=uuid.uuid4(),
            document_request_id=request_id,
            file_storage_key="",
            declared_mime_type=body.mime_type,
            declared_size_bytes=body.file_size_bytes,
            upload_status=UploadStatus.awaiting_upload,
        )
        evidence.file_storage_key = _raw_key(request, evidence.id)
        session.add(evidence)
        presigned = await storage.presign_upload(
            evidence.file_storage_key,
            body.mime_type,
            settings.evidence_max_bytes,
            settings.upload_url_ttl_seconds,
        )
        evidence_id = evidence.id

    return UploadUrlOut(
        evidence_id=evidence_id,
        upload_url=presigned.url,
        upload_fields=presigned.fields,
        expires_in=settings.upload_url_ttl_seconds,
    )


@router.post("/{evidence_id}/complete", response_model=CompleteOut)
async def complete_upload(
    request_id: uuid.UUID,
    evidence_id: uuid.UUID,
    principal: Annotated[Principal, Depends(get_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[ObjectStorage, Depends(get_storage)],
    scanner: Annotated[Scanner, Depends(get_scanner)],
) -> CompleteOut:
    async with user_session(principal.user_id) as session:
        request = await session.get(DocumentRequest, request_id)
        evidence = await session.get(SourceEvidence, evidence_id)
        if request is None or evidence is None or evidence.document_request_id != request_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "evidence_not_found")
        if evidence.upload_status == UploadStatus.validated:  # rejeu idempotent
            assert evidence.content_hash and evidence.review_status
            return CompleteOut(
                evidence_id=evidence.id,
                content_hash=evidence.content_hash,
                review_status=evidence.review_status,
            )
        if evidence.upload_status == UploadStatus.rejected:
            raise HTTPException(status.HTTP_409_CONFLICT, "evidence_rejected")
        raw_key, clean_key = evidence.file_storage_key, _clean_key(request, evidence_id)
        declared = evidence.declared_mime_type
        user_id = request.user_id

    error: EvidenceRejectedError | None = None
    clean = None
    size = await storage.size(raw_key)
    if size is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "file_not_uploaded")
    try:
        if size > settings.evidence_max_bytes:  # avant toute lecture en mémoire
            raise EvidenceRejectedError("file_too_large", "fichier trop volumineux")
        data = await storage.read(raw_key)
        clean = await asyncio.to_thread(sanitize, data, declared, settings.evidence_max_pixels)
        if not await scanner.is_clean(clean.data):
            raise EvidenceRejectedError("malware_detected", "fichier jugé dangereux")
    except EvidenceRejectedError as e:
        error = e
    except ScanUnavailableError:
        # Ni accepté ni rejeté: le client peut réessayer.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "scan_unavailable") from None

    if error is not None or clean is None:
        assert error is not None
        await storage.delete(raw_key)
        async with user_session(principal.user_id) as session:
            evidence = await session.get(SourceEvidence, evidence_id)
            assert evidence is not None
            evidence.upload_status = UploadStatus.rejected
            evidence.upload_error = error.code
            await notify(
                session,
                request_id=request_id,
                user_id=user_id,
                event_type=EventType.evidence_upload_failed,
                channels=(NotificationChannel.email, NotificationChannel.sms),
                discriminator=evidence_id,
            )
        log.info("evidence_rejected", evidence_id=str(evidence_id), code=error.code)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"code": error.code, "reason": error.citizen_reason},
        )

    await storage.write(clean_key, clean.data, clean.mime_type)
    await storage.delete(raw_key)
    content_hash = f"sha256:{clean.sha256}"
    async with user_session(principal.user_id) as session:
        evidence = await session.get(SourceEvidence, evidence_id)
        assert evidence is not None
        evidence.file_storage_key = clean_key
        evidence.mime_type = clean.mime_type
        evidence.content_hash = content_hash
        evidence.upload_status = UploadStatus.validated
        evidence.review_status = ReviewStatus.pending
        evidence.uploaded_at = datetime.now(UTC)
        await notify(
            session,
            request_id=request_id,
            user_id=user_id,
            event_type=EventType.evidence_received,
            channels=(NotificationChannel.in_app,),
            discriminator=evidence_id,
        )
    log.info("evidence_validated", evidence_id=str(evidence_id))
    return CompleteOut(
        evidence_id=evidence_id, content_hash=content_hash, review_status=ReviewStatus.pending
    )
