"""users, document_requests, document_request_status_history

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

APP_ROLE = "docuciv_app"
TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
USER = "NULLIF(current_setting('app.user_id', true), '')::uuid"

STATUSES = (
    "pending_reference_check",
    "reference_not_found",
    "pending_payment",
    "paid",
    "in_review",
    "in_progress",
    "issued",
    "rejected",
)


def upgrade() -> None:
    status = postgresql.ENUM(*STATUSES, name="request_status", create_type=False)
    postgresql.ENUM(*STATUSES, name="request_status").create(op.get_bind())

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("type", postgresql.ENUM("citizen", "business", name="user_type"), nullable=False),
        sa.Column("full_name", sa.String(200)),
        sa.Column("company_name", sa.String(200)),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("email", sa.String(320)),
        sa.Column("national_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "document_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "administration_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("administrations.id"),
            nullable=False,
        ),
        sa.Column(
            "document_type",
            postgresql.ENUM(
                "acte_naissance",
                "certificat_residence",
                "car",
                "permis_conduire",
                name="document_type",
            ),
            nullable=False,
        ),
        sa.Column("reference_document_id", sa.String(64), nullable=False),
        sa.Column("status", status, nullable=False),
        sa.Column("rejection_reason", sa.String(500)),
        sa.Column("estimated_ready_at", sa.DateTime(timezone=True)),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_document_requests_user_id", "document_requests", ["user_id"])
    op.create_index(
        "ix_document_requests_administration_id", "document_requests", ["administration_id"]
    )
    op.create_table(
        "document_request_status_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_requests.id"),
            nullable=False,
        ),
        sa.Column("from_status", status),
        sa.Column("to_status", status, nullable=False),
        sa.Column("reason", sa.String(500)),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_status_history_request_id", "document_request_status_history", ["document_request_id"]
    )

    # RLS: un citoyen voit ses lignes, un agent voit celles de son tenant (policies permissives
    # cumulées en OR). FORCE: le propriétaire de la table y est soumis aussi.
    for table in ("users", "document_requests", "document_request_status_history"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    op.execute(f"CREATE POLICY self_access ON users USING (id = {USER}) WITH CHECK (id = {USER})")
    op.execute(
        f"CREATE POLICY citizen_access ON document_requests "
        f"USING (user_id = {USER}) WITH CHECK (user_id = {USER})"
    )
    op.execute(
        f"CREATE POLICY tenant_isolation ON document_requests "
        f"USING (administration_id = {TENANT}) WITH CHECK (administration_id = {TENANT})"
    )
    # L'historique suit la visibilité de la demande (la sous-requête est elle-même soumise à RLS).
    op.execute(
        "CREATE POLICY follows_request ON document_request_status_history "
        "USING (EXISTS (SELECT 1 FROM document_requests r "
        "WHERE r.id = document_request_id)) "
        "WITH CHECK (EXISTS (SELECT 1 FROM document_requests r "
        "WHERE r.id = document_request_id))"
    )

    op.execute(f"GRANT SELECT, INSERT, UPDATE ON users TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON document_requests TO {APP_ROLE}")
    # Append-only (AGENTS.md / data-model): jamais d'UPDATE ni de DELETE.
    op.execute(f"GRANT SELECT, INSERT ON document_request_status_history TO {APP_ROLE}")

    # Un citoyen ne peut pas lire `administrations` (RLS tenant, contient api_key_hash). Cette
    # fonction n'expose qu'un booléen: l'administration existe, est active et émet des documents.
    op.execute(
        """
        CREATE FUNCTION issuer_accepts_requests(admin_id uuid) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
          SELECT EXISTS (
            SELECT 1 FROM administrations
            WHERE id = admin_id AND status = 'active' AND role IN ('issuer', 'both')
          )
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION issuer_accepts_requests(uuid) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION issuer_accepts_requests(uuid) TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS issuer_accepts_requests(uuid)")
    op.drop_table("document_request_status_history")
    op.drop_table("document_requests")
    op.drop_table("users")
    for enum in ("request_status", "document_type", "user_type"):
        op.execute(f"DROP TYPE IF EXISTS {enum}")
