"""reclamations (RLS citoyen + tenant) et notifications sans demande liée

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

APP_ROLE = "docuciv_app"
USER = "NULLIF(current_setting('app.user_id', true), '')::uuid"
TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
REQUEST_VISIBLE = "EXISTS (SELECT 1 FROM document_requests r WHERE r.id = document_request_id)"


def upgrade() -> None:
    category = postgresql.ENUM(
        "delay",
        "document_error",
        "payment_issue",
        "evidence_rejected_wrongly",
        "fraud_suspicion",
        "other",
        name="reclamation_category",
    )
    status = postgresql.ENUM(
        "open", "in_progress", "resolved", "rejected", "reopened", name="reclamation_status"
    )
    category.create(op.get_bind())
    status.create(op.get_bind())
    op.create_table(
        "reclamations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("administrations.id")),
        sa.Column(
            "document_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_requests.id"),
        ),
        sa.Column(
            "category",
            postgresql.ENUM(name="reclamation_category", create_type=False),
            nullable=False,
        ),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="reclamation_status", create_type=False),
            nullable=False,
        ),
        sa.Column("sla_response_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("handled_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("admin_agents.id")),
        sa.Column("response", sa.String(2000)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_reclamations_user_id", "reclamations", ["user_id"])
    op.create_index("ix_reclamations_tenant_id", "reclamations", ["tenant_id"])
    op.execute("ALTER TABLE reclamations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE reclamations FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY citizen_access ON reclamations "
        f"USING (user_id = {USER}) WITH CHECK (user_id = {USER})"
    )
    # tenant_id NULL (réclamation libre/transverse) ne correspond jamais: invisible des tenants.
    op.execute(
        f"CREATE POLICY tenant_isolation ON reclamations "
        f"USING (tenant_id = {TENANT}) WITH CHECK (tenant_id = {TENANT})"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON reclamations TO {APP_ROLE}")

    # Une réclamation libre n'a pas de demande: sa notification ne suit que le citoyen.
    op.execute("DROP POLICY follows_request ON notification_events")
    op.execute(
        f"CREATE POLICY follows_request ON notification_events "
        f"USING ({REQUEST_VISIBLE} OR (document_request_id IS NULL AND user_id = {USER})) "
        f"WITH CHECK ({REQUEST_VISIBLE} OR (document_request_id IS NULL AND user_id = {USER}))"
    )


def downgrade() -> None:
    op.execute("DROP POLICY follows_request ON notification_events")
    op.execute(
        f"CREATE POLICY follows_request ON notification_events "
        f"USING ({REQUEST_VISIBLE}) WITH CHECK ({REQUEST_VISIBLE})"
    )
    op.drop_table("reclamations")
    op.execute("DROP TYPE IF EXISTS reclamation_status")
    op.execute("DROP TYPE IF EXISTS reclamation_category")
