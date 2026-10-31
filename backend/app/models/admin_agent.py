import uuid
from enum import StrEnum

from sqlalchemy import Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin


class AdminAgentRole(StrEnum):
    issuer_agent = "issuer_agent"
    verifier_agent = "verifier_agent"
    tenant_admin = "tenant_admin"


class AdminAgent(Base, TenantMixin, TimestampMixin):
    """Example tenanted table — demonstrates the RLS pattern every future
    business table must follow (see docs/data-model.md §1, AGENTS.md règle 8)."""

    __tablename__ = "admin_agents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    role: Mapped[AdminAgentRole] = mapped_column(
        Enum(AdminAgentRole, name="admin_agent_role"), nullable=False
    )
