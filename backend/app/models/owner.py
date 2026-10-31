import uuid

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class OwnerUser(Base, TimestampMixin):
    """DocuCiv platform team account. No tenant_id — cross-tenant access only
    (see docs/data-model.md §1)."""

    __tablename__ = "owner_users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PlatformAuditLog(Base, TimestampMixin):
    """Append-only, non-deletable even by an Owner — every cross-tenant read
    or Owner action must be logged here with justification (AGENTS.md règle 8,
    docs/security.md §6)."""

    __tablename__ = "platform_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    target_tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    justification: Mapped[str | None] = mapped_column(String(2000), nullable=True)
