"""administrations + admin_agents avec Row-Level Security

Revision ID: 0001
Revises:
"""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

APP_ROLE = "docuciv_app"
# NULLIF: contexte absent -> NULL -> aucune ligne visible (fail closed), pas d'erreur de cast.
TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def _app_role_password() -> str:
    # Hors dev, le mot de passe vient exclusivement du secret injecté; jamais de défaut.
    password = os.environ.get("DOCUCIV_APP_DB_PASSWORD")
    if password:
        return password.replace("'", "''")
    if os.environ.get("DOCUCIV_ENVIRONMENT", "dev") == "dev":
        return "docuciv_app"
    raise RuntimeError("DOCUCIV_APP_DB_PASSWORD requis hors environnement dev")


def upgrade() -> None:
    op.execute(
        f"""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{_app_role_password()}'
              NOSUPERUSER NOBYPASSRLS;
          END IF;
        END $$;
        """
    )
    op.create_table(
        "administrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM("issuer", "verifier", "both", name="administration_role"),
            nullable=False,
        ),
        sa.Column("api_key_hash", sa.String(255)),
        sa.Column("subscription_tier", sa.String(50), nullable=False),
        sa.Column(
            "status", postgresql.ENUM("active", "suspended", name="tenant_status"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "admin_agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("administrations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM("issuer_agent", "verifier_agent", "tenant_admin", name="agent_role"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    for table, column in (("administrations", "id"), ("admin_agents", "tenant_id")):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({column} = {TENANT}) WITH CHECK ({column} = {TENANT})"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("admin_agents")
    op.drop_table("administrations")
    op.execute("DROP TYPE IF EXISTS agent_role")
    op.execute("DROP TYPE IF EXISTS administration_role")
    op.execute("DROP TYPE IF EXISTS tenant_status")
