"""Machine à états de DocumentRequest (docs/data-model.md §3). Seul point de mutation du statut."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DocumentRequest, DocumentRequestStatusHistory, RequestStatus

S = RequestStatus

ALLOWED: dict[RequestStatus, frozenset[RequestStatus]] = {
    S.pending_reference_check: frozenset({S.pending_payment, S.reference_not_found}),
    S.pending_payment: frozenset({S.paid}),
    S.paid: frozenset({S.in_review, S.rejected}),
    S.in_review: frozenset({S.in_progress, S.rejected}),
    S.in_progress: frozenset({S.issued, S.rejected}),
    S.reference_not_found: frozenset(),
    S.issued: frozenset(),
    S.rejected: frozenset(),
}


class InvalidTransitionError(Exception):
    pass


async def transition(
    session: AsyncSession,
    request_id: uuid.UUID,
    expected_from: RequestStatus,
    to: RequestStatus,
    reason: str | None = None,
) -> DocumentRequest | None:
    """Fait passer la demande de `expected_from` à `to` et journalise l'historique.

    Verrouille la ligne (FOR UPDATE) et retourne None si le statut courant n'est plus
    `expected_from`: un rejeu ou une course entre workers devient un no-op idempotent.
    """
    if to not in ALLOWED[expected_from]:
        raise InvalidTransitionError(f"{expected_from} -> {to}")
    request = await session.scalar(
        select(DocumentRequest).where(DocumentRequest.id == request_id).with_for_update()
    )
    if request is None or request.status != expected_from:
        return None
    request.status = to
    session.add(
        DocumentRequestStatusHistory(
            document_request_id=request.id, from_status=expected_from, to_status=to, reason=reason
        )
    )
    await session.flush()
    return request
