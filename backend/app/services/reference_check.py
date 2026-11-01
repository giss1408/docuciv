"""Contrôle d'existence du document de référence avant paiement (docs/notifications.md §3)."""

import asyncio
import uuid
from typing import Protocol

import structlog

from app.db import tenant_session
from app.models import (
    DocumentRequest,
    DocumentType,
    NotificationChannel,
    ReferenceCheckResult,
    RequestStatus,
)
from app.services.notifications import EventType, notify
from app.services.state_machine import transition

log = structlog.get_logger()

CHECK_TIMEOUT_SECONDS = 10


class ReferenceChecker(Protocol):
    async def check(
        self, administration_id: uuid.UUID, document_type: DocumentType, reference: str
    ) -> ReferenceCheckResult: ...


class UnverifiableChecker:
    """Défaut MVP: les tenants pilotes n'ont pas d'API d'intégration (notifications.md §3)."""

    async def check(
        self, administration_id: uuid.UUID, document_type: DocumentType, reference: str
    ) -> ReferenceCheckResult:
        return ReferenceCheckResult.unverifiable


def get_reference_checker() -> ReferenceChecker:
    return UnverifiableChecker()


async def run_reference_check(
    request_id: uuid.UUID, administration_id: uuid.UUID, checker: ReferenceChecker
) -> None:
    """Idempotent: sans effet si la demande n'est plus en `pending_reference_check`.

    S'exécute avec le contexte du tenant émetteur (RLS), jamais avec un rôle contournant la RLS.
    """
    async with tenant_session(administration_id) as session:
        request = await session.get(DocumentRequest, request_id)
        if request is None or request.status != RequestStatus.pending_reference_check:
            return
        document_type, reference = request.document_type, request.reference_document_id

    # Appel externe hors transaction: ne pas garder un verrou pendant une I/O réseau.
    try:
        result = await asyncio.wait_for(
            checker.check(administration_id, document_type, reference), CHECK_TIMEOUT_SECONDS
        )
    except Exception:
        # La demande reste en pending_reference_check; le job de relance la reprendra.
        # Jamais de basculement en pending_payment (donc de paiement) sur erreur.
        log.warning("reference_check_failed", request_id=str(request_id))
        return

    to = (
        RequestStatus.reference_not_found
        if result == ReferenceCheckResult.not_found
        else RequestStatus.pending_payment
    )
    event, channels = {
        ReferenceCheckResult.not_found: (
            EventType.reference_not_found,
            (NotificationChannel.email, NotificationChannel.sms),
        ),
        ReferenceCheckResult.found: (EventType.reference_found, (NotificationChannel.in_app,)),
        ReferenceCheckResult.unverifiable: (
            EventType.reference_unverifiable,
            (NotificationChannel.in_app,),
        ),
    }[result]

    async with tenant_session(administration_id) as session:
        request = await transition(
            session,
            request_id,
            RequestStatus.pending_reference_check,
            to,
            reason=f"reference_{result}",
        )
        if request is None:  # déjà traitée par un autre worker
            return
        request.reference_check = result
        await notify(
            session,
            request_id=request_id,
            user_id=request.user_id,
            event_type=event,
            channels=channels,
        )
    log.info("reference_checked", request_id=str(request_id), result=str(result))
