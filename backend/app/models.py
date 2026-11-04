import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AdministrationRole(enum.StrEnum):
    issuer = "issuer"
    verifier = "verifier"
    both = "both"


class TenantStatus(enum.StrEnum):
    active = "active"
    suspended = "suspended"


class AgentRole(enum.StrEnum):
    issuer_agent = "issuer_agent"
    verifier_agent = "verifier_agent"
    tenant_admin = "tenant_admin"


class Administration(Base):
    """Tenant. Son `id` joue le rôle de tenant_id pour la RLS."""

    __tablename__ = "administrations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[AdministrationRole] = mapped_column(
        Enum(AdministrationRole, name="administration_role")
    )
    api_key_hash: Mapped[str | None] = mapped_column(String(255))
    subscription_tier: Mapped[str] = mapped_column(String(50), default="standard")
    status: Mapped[TenantStatus] = mapped_column(
        Enum(TenantStatus, name="tenant_status"), default=TenantStatus.active
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdminAgent(Base):
    __tablename__ = "admin_agents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("administrations.id"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[AgentRole] = mapped_column(Enum(AgentRole, name="agent_role"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserType(enum.StrEnum):
    citizen = "citizen"
    business = "business"


class DocumentType(enum.StrEnum):
    acte_naissance = "acte_naissance"
    certificat_residence = "certificat_residence"
    car = "car"
    permis_conduire = "permis_conduire"


class RequestStatus(enum.StrEnum):
    pending_reference_check = "pending_reference_check"
    reference_not_found = "reference_not_found"
    pending_payment = "pending_payment"
    paid = "paid"
    in_review = "in_review"
    in_progress = "in_progress"
    issued = "issued"
    rejected = "rejected"


class ReferenceCheckResult(enum.StrEnum):
    found = "found"
    not_found = "not_found"
    unverifiable = "unverifiable"


class NotificationChannel(enum.StrEnum):
    email = "email"
    sms = "sms"
    push = "push"
    in_app = "in_app"


class NotificationSendStatus(enum.StrEnum):
    # `pending` = enregistré, en attente d'envoi par le service Notification (hors spec initiale).
    pending = "pending"
    sent = "sent"
    failed = "failed"
    skipped_duplicate = "skipped_duplicate"


class UploadStatus(enum.StrEnum):
    awaiting_upload = "awaiting_upload"
    validated = "validated"
    rejected = "rejected"


class ReviewStatus(enum.StrEnum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"


class ProcessingDelayConfig(Base):
    """Délai de traitement cible par tenant et type de document (notifications.md §4)."""

    __tablename__ = "processing_delay_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    administration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("administrations.id"), index=True
    )
    document_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType, name="document_type"))
    business_days: Mapped[int] = mapped_column()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[UserType] = mapped_column(Enum(UserType, name="user_type"))
    full_name: Mapped[str | None] = mapped_column(String(200))
    company_name: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(320))
    national_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentRequest(Base):
    """`administration_id` est la colonne tenant (administration émettrice) pour la RLS."""

    __tablename__ = "document_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    administration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("administrations.id"), index=True
    )
    document_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType, name="document_type"))
    reference_document_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[RequestStatus] = mapped_column(Enum(RequestStatus, name="request_status"))
    reference_check: Mapped[ReferenceCheckResult | None] = mapped_column(
        Enum(ReferenceCheckResult, name="reference_check_result")
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(500))
    estimated_ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Posé une fois par le job de relance: idempotence + file de relance de l'agent.
    overdue_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DocumentRequestStatusHistory(Base):
    """Append-only: le rôle applicatif n'a que SELECT/INSERT sur cette table."""

    __tablename__ = "document_request_status_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_requests.id"), index=True
    )
    from_status: Mapped[RequestStatus | None] = mapped_column(
        Enum(RequestStatus, name="request_status")
    )
    to_status: Mapped[RequestStatus] = mapped_column(Enum(RequestStatus, name="request_status"))
    reason: Mapped[str | None] = mapped_column(String(500))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationEvent(Base):
    """Trace d'une notification. Jamais le contenu du message (PII, notifications.md §7)."""

    __tablename__ = "notification_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_requests.id"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    # str (pas un enum PG) pour ajouter un type d'événement sans migration de type.
    event_type: Mapped[str] = mapped_column(String(64))
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="notification_channel")
    )
    send_status: Mapped[NotificationSendStatus] = mapped_column(
        Enum(NotificationSendStatus, name="notification_send_status")
    )
    idempotency_key: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceEvidence(Base):
    """Pièce justificative (photo/scan). Fichier sur S3 uniquement, jamais en base.

    `upload_status` couvre la validation technique (complete); `review_status` n'est renseigné
    qu'une fois le fichier validé et attend l'agent émetteur (AGENTS.md règle 12).
    """

    __tablename__ = "source_evidence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_requests.id"), index=True
    )
    file_storage_key: Mapped[str] = mapped_column(String(300))
    declared_mime_type: Mapped[str] = mapped_column(String(64))
    declared_size_bytes: Mapped[int] = mapped_column()
    mime_type: Mapped[str | None] = mapped_column(String(64))  # type réel, après validation
    content_hash: Mapped[str | None] = mapped_column(String(80))
    upload_status: Mapped[UploadStatus] = mapped_column(Enum(UploadStatus, name="upload_status"))
    upload_error: Mapped[str | None] = mapped_column(String(64))
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_agents.id")
    )
    review_status: Mapped[ReviewStatus | None] = mapped_column(
        Enum(ReviewStatus, name="review_status")
    )
    review_notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReclamationCategory(enum.StrEnum):
    delay = "delay"
    document_error = "document_error"
    payment_issue = "payment_issue"
    evidence_rejected_wrongly = "evidence_rejected_wrongly"
    fraud_suspicion = "fraud_suspicion"
    other = "other"


class ReclamationStatus(enum.StrEnum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    rejected = "rejected"
    reopened = "reopened"


class Reclamation(Base):
    """Réclamation citoyen (notifications.md §6). `tenant_id` = administration de la demande liée.

    NULL pour une réclamation libre ou transverse: invisible des tenants, réservée à l'Owner.
    """

    __tablename__ = "reclamations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("administrations.id"), index=True
    )
    document_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_requests.id")
    )
    category: Mapped[ReclamationCategory] = mapped_column(
        Enum(ReclamationCategory, name="reclamation_category")
    )
    description: Mapped[str] = mapped_column(String(2000))
    status: Mapped[ReclamationStatus] = mapped_column(
        Enum(ReclamationStatus, name="reclamation_status")
    )
    sla_response_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    handled_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_agents.id")
    )
    response: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
