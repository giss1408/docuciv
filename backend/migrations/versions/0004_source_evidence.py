"""source_evidence

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

APP_ROLE = "docuciv_app"


def upgrade() -> None:
    op.create_table(
        "source_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_requests.id"),
            nullable=False,
        ),
        sa.Column("file_storage_key", sa.String(300), nullable=False),
        sa.Column("declared_mime_type", sa.String(64), nullable=False),
        sa.Column("declared_size_bytes", sa.Integer, nullable=False),
        sa.Column("mime_type", sa.String(64)),
        sa.Column("content_hash", sa.String(80)),
        sa.Column(
            "upload_status",
            postgresql.ENUM("awaiting_upload", "validated", "rejected", name="upload_status"),
            nullable=False,
        ),
        sa.Column("upload_error", sa.String(64)),
        sa.Column("uploaded_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("admin_agents.id")),
        sa.Column(
            "review_status",
            postgresql.ENUM("pending", "accepted", "rejected", name="review_status"),
        ),
        sa.Column("review_notes", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_source_evidence_document_request_id", "source_evidence", ["document_request_id"]
    )
    op.execute("ALTER TABLE source_evidence ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE source_evidence FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY follows_request ON source_evidence "
        "USING (EXISTS (SELECT 1 FROM document_requests r WHERE r.id = document_request_id)) "
        "WITH CHECK (EXISTS (SELECT 1 FROM document_requests r WHERE r.id = document_request_id))"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON source_evidence TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("source_evidence")
    op.execute("DROP TYPE IF EXISTS review_status")
    op.execute("DROP TYPE IF EXISTS upload_status")
