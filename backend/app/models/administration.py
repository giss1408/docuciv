import uuid
from enum import StrEnum

from sqlalchemy import Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AdministrationRole(StrEnum):
    issuer = "issuer"
    verifier = "verifier"
    both = "both"


class AdministrationStatus(StrEnum):
    active = "active"
    suspended = "suspended"


class Administration(Base, TimestampMixin):
    """A tenant (émetteur/requérante). This table has no tenant_id of its own —
    it IS the tenant — and is read cross-tenant only by the Owner role (see
    docs/data-model.md §1/§4)."""

    __tablename__ = "administrations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[AdministrationRole] = mapped_column(
        Enum(AdministrationRole, name="administration_role"), nullable=False
    )
    api_key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    subscription_tier: Mapped[str] = mapped_column(String(50), nullable=False, default="standard")
    status: Mapped[AdministrationStatus] = mapped_column(
        Enum(AdministrationStatus, name="administration_status"),
        nullable=False,
        default=AdministrationStatus.active,
    )
