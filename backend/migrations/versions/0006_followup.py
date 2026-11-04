"""overdue_notified_at + fonction de recherche des demandes à relancer

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

APP_ROLE = "docuciv_app"

# Seule brèche contrôlée dans la RLS (AGENTS.md règle 8): le job de relance doit trouver les
# demandes de tous les tenants. La fonction ne renvoie que des identifiants (aucune PII), et le
# traitement de chaque demande repasse par tenant_session. Elle appartient au rôle de migration,
# qui contourne la RLS (superuser ou BYPASSRLS); sinon elle échoue plutôt que de filtrer.
FUNCTION = """
CREATE OR REPLACE FUNCTION docuciv_find_followups(stale_before timestamptz)
RETURNS TABLE (request_id uuid, administration_id uuid, kind text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT r.id, r.administration_id, 'overdue'
    FROM document_requests r
   WHERE r.status = 'in_progress'
     AND r.estimated_ready_at < now()
     AND r.overdue_notified_at IS NULL
  UNION ALL
  SELECT r.id, r.administration_id, 'stuck_reference_check'
    FROM document_requests r
   WHERE r.status = 'pending_reference_check'
     AND r.created_at < stale_before
$$
"""


def upgrade() -> None:
    op.add_column("document_requests", sa.Column("overdue_notified_at", sa.DateTime(timezone=True)))
    op.execute(FUNCTION)
    op.execute("REVOKE ALL ON FUNCTION docuciv_find_followups(timestamptz) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION docuciv_find_followups(timestamptz) TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS docuciv_find_followups(timestamptz)")
    op.drop_column("document_requests", "overdue_notified_at")
