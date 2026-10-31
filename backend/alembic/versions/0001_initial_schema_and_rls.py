"""initial schema: administrations, admin_agents, owner tables + RLS policy

Revision ID: 0001
Revises:
Create Date: 2026-10-31

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "administrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("issuer", "verifier", "both", name="administration_role"),
            nullable=False,
        ),
        sa.Column("api_key_hash", sa.String(255), nullable=False),
        sa.Column("subscription_tier", sa.String(50), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "suspended", name="administration_status"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "admin_agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column(
            "role",
            sa.Enum("issuer_agent", "verifier_agent", "tenant_admin", name="admin_agent_role"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["administrations.id"]),
    )
    op.create_index("ix_admin_agents_tenant_id", "admin_agents", ["tenant_id"])

    op.create_table(
        "owner_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "platform_audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(255), nullable=False),
        sa.Column("target_tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("justification", sa.String(2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Row-Level Security: tenant isolation enforced in PostgreSQL, never only
    # at the application level (AGENTS.md règle 8, docs/security.md §2/§4).
    # The app sets `app.current_tenant_id` per request/session (see
    # app/db/session.py); the `docuciv_owner` DB role bypasses this policy
    # entirely for explicit cross-tenant supervision (always logged to
    # PlatformAuditLog at the application layer).
    op.execute("ALTER TABLE admin_agents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE admin_agents FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation_admin_agents ON admin_agents
        USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
        WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_admin_agents ON admin_agents")
    op.drop_table("platform_audit_log")
    op.drop_table("owner_users")
    op.drop_index("ix_admin_agents_tenant_id", table_name="admin_agents")
    op.drop_table("admin_agents")
    op.drop_table("administrations")
    op.execute("DROP TYPE IF EXISTS admin_agent_role")
    op.execute("DROP TYPE IF EXISTS administration_status")
    op.execute("DROP TYPE IF EXISTS administration_role")
