"""Règles de la revue de pièce justificative (docs/notifications.md §2 #6, §4)."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import (
    DocumentType,
    ProcessingDelayConfig,
    RequestStatus,
    SourceEvidence,
    UploadStatus,
)
from app.services.state_machine import transition


def add_business_days(start: datetime, days: int) -> datetime:
    """Ajoute des jours ouvrés (lun-ven). Les jours fériés ivoiriens ne sont pas gérés."""
    current = start
    while days > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            days -= 1
    return current


async def estimate_ready_at(
    session: AsyncSession,
    administration_id: uuid.UUID,
    document_type: DocumentType,
    settings: Settings,
    now: datetime | None = None,
) -> datetime:
    days = await session.scalar(
        select(ProcessingDelayConfig.business_days).where(
            ProcessingDelayConfig.administration_id == administration_id,
            ProcessingDelayConfig.document_type == document_type,
        )
    )
    return add_business_days(
        now or datetime.now(UTC), days or settings.default_processing_business_days
    )


async def enter_review_if_ready(session: AsyncSession, request_id: uuid.UUID) -> bool:
    """paid + au moins une pièce validée -> in_review (notifications.md §2, note d'ordre).

    Appelée à chaque fait déclencheur (pièce validée ici, paiement confirmé en Phase 3):
    l'ordre d'arrivée n'importe pas, et l'appel est un no-op tant que la condition manque.
    """
    validated = await session.scalar(
        select(func.count())
        .select_from(SourceEvidence)
        .where(
            SourceEvidence.document_request_id == request_id,
            SourceEvidence.upload_status == UploadStatus.validated,
        )
    )
    if not validated:
        return False
    moved = await transition(
        session,
        request_id,
        RequestStatus.paid,
        RequestStatus.in_review,
        reason="evidence_and_payment",
    )
    return moved is not None
