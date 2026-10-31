"""create least-privilege app/owner DB roles for RLS enforcement

PostgreSQL superusers and table owners always bypass Row-Level Security,
even with FORCE ROW LEVEL SECURITY (docs/security.md §4) — discovered
while writing the BOLA integration test (tests/test_rls_isolation.py):
the migration-running role was a superuser and silently saw every tenant's
rows. The application must never connect as the migration/owner role.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-31

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Passwords are placeholders substituted at deploy time from Vault/Secrets
# Manager (docs/security.md §10) — never real secrets in a migration file.
_APP_ROLE = "docuciv_app"
_OWNER_ROLE = "docuciv_owner"


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{_APP_ROLE}') THEN
                CREATE ROLE {_APP_ROLE} LOGIN PASSWORD 'replace-at-deploy-time' NOSUPERUSER;
            END IF;
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{_OWNER_ROLE}') THEN
                CREATE ROLE {_OWNER_ROLE} LOGIN PASSWORD 'replace-at-deploy-time' NOSUPERUSER;
            END IF;
        END
        $$;
        """
    )

    # docuciv_app: the role every tenant-scoped request connects as. RLS
    # applies to it in full because it is neither a superuser nor the table
    # owner (app.db.session.get_scoped_db).
    op.execute(
        f"""
        DO $$
        BEGIN
            EXECUTE format('GRANT CONNECT ON DATABASE %I TO {_APP_ROLE}', current_database());
        END
        $$;
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {_APP_ROLE}")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON admin_agents, administrations TO {_APP_ROLE}"
    )

    # docuciv_owner: the only role allowed to read across tenants, and only
    # via app.core.owner_access, which always writes a justified
    # PlatformAuditLog entry first (docs/security.md §6). BYPASSRLS is
    # explicit and narrow — scoped to this one dedicated role, not to the
    # migration/admin role used for schema changes.
    op.execute(f"ALTER ROLE {_OWNER_ROLE} BYPASSRLS")
    op.execute(
        f"""
        DO $$
        BEGIN
            EXECUTE format('GRANT CONNECT ON DATABASE %I TO {_OWNER_ROLE}', current_database());
        END
        $$;
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {_OWNER_ROLE}")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {_OWNER_ROLE}"
    )


def downgrade() -> None:
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {_OWNER_ROLE}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {_APP_ROLE}")
    op.execute(f"REVOKE ALL ON SCHEMA public FROM {_OWNER_ROLE}")
    op.execute(f"REVOKE ALL ON SCHEMA public FROM {_APP_ROLE}")
    op.execute(
        f"""
        DO $$
        BEGIN
            EXECUTE format('REVOKE ALL ON DATABASE %I FROM {_OWNER_ROLE}', current_database());
            EXECUTE format('REVOKE ALL ON DATABASE %I FROM {_APP_ROLE}', current_database());
        END
        $$;
        """
    )
    op.execute(f"DROP ROLE IF EXISTS {_OWNER_ROLE}")
    op.execute(f"DROP ROLE IF EXISTS {_APP_ROLE}")
