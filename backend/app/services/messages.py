"""Texte des notifications (docs/notifications.md §2), rendu à la demande.

Le texte n'est jamais stocké (PII, §7) et ne contient ni nom, ni numéro d'identité, ni contenu
de document: uniquement la référence courte de la demande, le type de document, le nom de
l'administration, des dates et — pour un rejet — le motif écrit par l'agent.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

from app.models import DocumentType
from app.services.notifications import EventType

DOCUMENT_LABELS = {
    DocumentType.acte_naissance: "extrait d'acte de naissance",
    DocumentType.certificat_residence: "certificat de résidence",
    DocumentType.car: "document CAR",
    DocumentType.permis_conduire: "permis de conduire",
}

_MONTHS = (
    "janvier février mars avril mai juin juillet août septembre octobre novembre décembre"
).split()


@dataclass(frozen=True)
class MessageContext:
    request_id: uuid.UUID
    document_type: DocumentType
    administration: str
    estimated_ready_at: datetime | None = None
    rejection_reason: str | None = None

    @property
    def ref(self) -> str:
        return str(self.request_id)[:8].upper()


def french_date(d: datetime) -> str:
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year}"


def render_message(event_type: str, ctx: MessageContext) -> str:
    doc = DOCUMENT_LABELS[ctx.document_type]
    ref = ctx.ref
    ready = french_date(ctx.estimated_ready_at) if ctx.estimated_ready_at else "à confirmer"
    reason = ctx.rejection_reason or "pièce non conforme"
    templates = {
        EventType.request_created: f"Votre demande #{ref} ({doc}) a bien été enregistrée.",
        EventType.reference_found: (
            f"Le document de référence de votre demande #{ref} a été trouvé. "
            "Vous pouvez ajouter votre pièce justificative puis procéder au paiement."
        ),
        EventType.reference_unverifiable: (
            f"Votre demande #{ref} est enregistrée. {ctx.administration} vérifiera "
            "votre document de référence. Vous pouvez poursuivre votre démarche."
        ),
        EventType.reference_not_found: (
            f"Nous n'avons pas trouvé le document de référence de votre demande #{ref}. "
            "Aucun paiement n'est demandé. Vérifiez le numéro et refaites une demande."
        ),
        EventType.evidence_upload_failed: (
            f"L'envoi de votre pièce justificative pour la demande #{ref} a échoué. "
            "Veuillez réessayer avec une photo nette."
        ),
        EventType.evidence_received: (
            f"Nous avons bien reçu votre pièce justificative pour la demande #{ref}."
        ),
        EventType.evidence_rejected_review: (
            f"Votre demande #{ref} n'a pas pu être validée : {reason}. "
            "Vous pouvez soumettre une nouvelle demande avec une photo corrigée."
        ),
        EventType.processing_started: (
            f"Votre document ({doc}) est en cours de préparation par {ctx.administration}. "
            f"Délai estimé : {ready}. Vous serez notifié dès qu'il sera prêt."
        ),
        EventType.request_overdue: (
            f"Votre demande #{ref} prend plus de temps que prévu. "
            f"Nouveau délai estimé : {ready}. Nous vous présentons nos excuses pour l'attente."
        ),
        EventType.reclamation_received: (
            f"Votre réclamation concernant la demande #{ref} a été enregistrée. "
            "Nous vous répondrons dans les meilleurs délais."
        ),
        EventType.reclamation_answered: (
            f"Une réponse à votre réclamation concernant la demande #{ref} "
            "est disponible dans l'application."
        ),
    }
    return f"DocuCiv : {templates[EventType(event_type)]}"


def whatsapp_url(phone: str, message: str) -> str | None:
    """Lien wa.me avec message prérempli: l'agent l'ouvre et envoie lui-même le message."""
    digits = "".join(c for c in phone if c.isdigit())
    if not 8 <= len(digits) <= 15:
        return None
    return f"https://wa.me/{digits}?text={quote(message)}"
