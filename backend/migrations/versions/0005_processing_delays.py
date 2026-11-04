"""processing_delay_configs

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

APP_ROLE = "docuciv_app"
TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "processing_delay_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "administration_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("administrations.id"),
            nullable=False,
        ),
        sa.Column(
            "document_type",
            postgresql.ENUM(name="document_type", create_type=False),
            nullable=False,
        ),
        sa.Column("business_days", sa.Integer, nullable=False),
        sa.CheckConstraint("business_days > 0", name="ck_delay_positive"),
        sa.UniqueConstraint("administration_id", "document_type", name="uq_delay_per_type"),
    )
    op.execute("ALTER TABLE processing_delay_configs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE processing_delay_configs FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON processing_delay_configs "
        f"USING (administration_id = {TENANT}) WITH CHECK (administration_id = {TENANT})"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON processing_delay_configs TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("processing_delay_configs")
