"""fonctions d'envoi des notifications (lecture des pending, changement d'état atomique)

Revision ID: 0008
Revises: 0007
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

APP_ROLE = "docuciv_app"

# Le worker d'envoi traite les notifications de tous les tenants: même brèche contrôlée que
# docuciv_find_followups (0006). Les fonctions n'exposent que des identifiants et n'écrivent que
# send_status; notification_events reste sans UPDATE/DELETE pour le rôle applicatif.
PENDING = """
CREATE OR REPLACE FUNCTION docuciv_pending_notifications(max_rows int)
RETURNS TABLE (id uuid, user_id uuid, document_request_id uuid, event_type text,
               channel text, idempotency_key text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT n.id, n.user_id, n.document_request_id, n.event_type, n.channel::text,
         n.idempotency_key
    FROM notification_events n
   WHERE n.send_status = 'pending'
   ORDER BY n.created_at, n.id
   LIMIT max_rows
$$
"""

# Compare-and-set: un seul worker obtient `true` pour une transition donnée.
SET_STATUS = """
CREATE OR REPLACE FUNCTION docuciv_set_notification_status(
  event_id uuid, expected text, new_status text)
RETURNS boolean
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  WITH updated AS (
    UPDATE notification_events
       SET send_status = new_status::notification_send_status
     WHERE id = event_id
       AND send_status = expected::notification_send_status
       AND new_status IN ('sent', 'failed')
    RETURNING 1
  )
  SELECT EXISTS (SELECT 1 FROM updated)
$$
"""


def upgrade() -> None:
    op.execute(PENDING)
    op.execute(SET_STATUS)
    for sig in (
        "docuciv_pending_notifications(int)",
        "docuciv_set_notification_status(uuid, text, text)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {sig} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS docuciv_set_notification_status(uuid, text, text)")
    op.execute("DROP FUNCTION IF EXISTS docuciv_pending_notifications(int)")
