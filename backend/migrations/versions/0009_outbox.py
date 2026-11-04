"""accès restreint de l'agent au téléphone du citoyen et à l'acquittement d'un envoi

Revision ID: 0009
Revises: 0008
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

APP_ROLE = "docuciv_app"

# `users` est invisible des tenants (RLS). L'agent doit pouvoir ouvrir WhatsApp vers le citoyen
# de SES demandes: la fonction ne renvoie que le téléphone, et seulement si la demande appartient
# au tenant fourni. Même brèche contrôlée que 0006/0008 (AGENTS.md règle 8).
PHONE = """
CREATE OR REPLACE FUNCTION docuciv_request_phone(req_id uuid, tenant uuid)
RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT u.phone
    FROM document_requests r JOIN users u ON u.id = r.user_id
   WHERE r.id = req_id AND r.administration_id = tenant
$$
"""

# L'agent acquitte « envoyé »: uniquement une notification sms en attente de SES demandes.
ACK = """
CREATE OR REPLACE FUNCTION docuciv_ack_outbox(event_id uuid, tenant uuid)
RETURNS boolean
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  WITH updated AS (
    UPDATE notification_events n
       SET send_status = 'sent'
      FROM document_requests r
     WHERE n.id = event_id
       AND n.document_request_id = r.id
       AND r.administration_id = tenant
       AND n.channel = 'sms'
       AND n.send_status = 'pending'
    RETURNING 1
  )
  SELECT EXISTS (SELECT 1 FROM updated)
$$
"""


PENDING_V2 = """
CREATE OR REPLACE FUNCTION docuciv_pending_notifications(
  max_rows int, skip_channels text[] DEFAULT '{}')
RETURNS TABLE (id uuid, user_id uuid, document_request_id uuid, event_type text,
               channel text, idempotency_key text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT n.id, n.user_id, n.document_request_id, n.event_type, n.channel::text,
         n.idempotency_key
    FROM notification_events n
   WHERE n.send_status = 'pending' AND NOT (n.channel::text = ANY (skip_channels))
   ORDER BY n.created_at, n.id
   LIMIT max_rows
$$
"""

PENDING_V1 = """
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


def upgrade() -> None:
    # Les canaux « manuels » (SMS/WhatsApp) ne doivent pas occuper le lot du dispatcher.
    op.execute("DROP FUNCTION IF EXISTS docuciv_pending_notifications(int)")
    op.execute(PENDING_V2)
    op.execute(PHONE)
    op.execute(ACK)
    for sig in (
        "docuciv_request_phone(uuid, uuid)",
        "docuciv_ack_outbox(uuid, uuid)",
        "docuciv_pending_notifications(int, text[])",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {sig} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS docuciv_pending_notifications(int, text[])")
    op.execute(PENDING_V1)
    op.execute(f"GRANT EXECUTE ON FUNCTION docuciv_pending_notifications(int) TO {APP_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION docuciv_pending_notifications(int) FROM PUBLIC")
    op.execute("DROP FUNCTION IF EXISTS docuciv_ack_outbox(uuid, uuid)")
    op.execute("DROP FUNCTION IF EXISTS docuciv_request_phone(uuid, uuid)")
