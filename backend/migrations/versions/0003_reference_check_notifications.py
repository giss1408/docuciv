"""reference_check sur document_requests + notification_events

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

APP_ROLE = "docuciv_app"


def upgrade() -> None:
    check = postgresql.ENUM("found", "not_found", "unverifiable", name="reference_check_result")
    check.create(op.get_bind())
    op.add_column(
        "document_requests",
        sa.Column(
            "reference_check", postgresql.ENUM(name="reference_check_result", create_type=False)
        ),
    )

    channel = postgresql.ENUM("email", "sms", "push", "in_app", name="notification_channel")
    send_status = postgresql.ENUM(
        "pending", "sent", "failed", "skipped_duplicate", name="notification_send_status"
    )
    op.create_table(
        "notification_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_requests.id"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("channel", channel, nullable=False),
        sa.Column("send_status", send_status, nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_notification_events_document_request_id",
        "notification_events",
        ["document_request_id"],
    )
    # Idempotence (notifications.md §1): au plus un envoi réel par (clé, canal); les doublons
    # sont tracés en `skipped_duplicate`, hors de la contrainte.
    op.execute(
        "CREATE UNIQUE INDEX uq_notification_idempotency ON notification_events "
        "(idempotency_key, channel) WHERE send_status <> 'skipped_duplicate'"
    )

    op.execute("ALTER TABLE notification_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE notification_events FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY follows_request ON notification_events "
        "USING (EXISTS (SELECT 1 FROM document_requests r WHERE r.id = document_request_id)) "
        "WITH CHECK (EXISTS (SELECT 1 FROM document_requests r WHERE r.id = document_request_id))"
    )
    # Append-only: l'état d'envoi final sera porté par de nouvelles lignes, jamais un UPDATE.
    op.execute(f"GRANT SELECT, INSERT ON notification_events TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("notification_events")
    op.drop_column("document_requests", "reference_check")
    for enum in ("notification_send_status", "notification_channel", "reference_check_result"):
        op.execute(f"DROP TYPE IF EXISTS {enum}")
