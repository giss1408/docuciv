import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
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
