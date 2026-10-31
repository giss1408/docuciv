"""BOLA / tenant-isolation integration test (AGENTS.md règle 8,
docs/security.md §4): proves the Row-Level Security policy on
`admin_agents`, not just an application-level WHERE clause, blocks
cross-tenant reads at the database level.

Requires a real PostgreSQL instance — skipped automatically if
DOCUCIV_TEST_DATABASE_URL isn't set (e.g. no Docker available). This is an
integration test, not a smoke test; see docs/workflow.md §1 for the
unit/smoke-vs-e2e distinction — it's kept here because it directly
implements a règle 8 merge gate, not a full user journey.
"""

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from alembic.config import Config

TEST_DB_URL = os.environ.get("DOCUCIV_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DB_URL, reason="DOCUCIV_TEST_DATABASE_URL not set — no PostgreSQL available"
)


@pytest.fixture(scope="module")
def migrated_db() -> str:
    assert TEST_DB_URL is not None
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", TEST_DB_URL)
    command.upgrade(config, "head")
    yield TEST_DB_URL
    command.downgrade(config, "base")


def _as_app_role(url: str) -> str:
    """RLS is bypassed entirely for superusers/table owners, so the test
    must connect as the same least-privilege `docuciv_app` role the real
    application uses (alembic/versions/0002), not as the migration role."""
    from sqlalchemy.engine import make_url

    url_obj = make_url(url).set(username="docuciv_app", password="replace-at-deploy-time")
    return url_obj.render_as_string(hide_password=False)


async def test_tenant_cannot_read_another_tenants_admin_agents(migrated_db: str) -> None:
    admin_engine = create_async_engine(migrated_db)
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    async with admin_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO administrations (id, name, role, api_key_hash, "
                "subscription_tier, status) VALUES "
                "(:id, 'Tenant A', 'issuer', 'hash', 'standard', 'active')"
            ),
            {"id": tenant_a},
        )
        await conn.execute(
            text(
                "INSERT INTO administrations (id, name, role, api_key_hash, "
                "subscription_tier, status) VALUES "
                "(:id, 'Tenant B', 'issuer', 'hash', 'standard', 'active')"
            ),
            {"id": tenant_b},
        )
        await conn.execute(
            text(
                "INSERT INTO admin_agents (id, tenant_id, full_name, email, role) VALUES "
                "(:id, :tenant_id, 'Agent B', 'agent-b@example.com', 'issuer_agent')"
            ),
            {"id": uuid.uuid4(), "tenant_id": tenant_b},
        )
    await admin_engine.dispose()

    app_engine = create_async_engine(_as_app_role(migrated_db))

    # Simulate tenant A's session context (what app.db.session.tenant_session does).
    async with app_engine.connect() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant_id', :tid, false)"), {"tid": str(tenant_a)}
        )
        result = await conn.execute(text("SELECT * FROM admin_agents"))
        rows = result.fetchall()

    assert rows == [], "RLS policy must hide tenant B's rows from a tenant A session"

    async with app_engine.connect() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant_id', :tid, false)"), {"tid": str(tenant_b)}
        )
        result = await conn.execute(text("SELECT * FROM admin_agents"))
        rows = result.fetchall()

    assert len(rows) == 1, "Tenant B must still see its own row"

    await app_engine.dispose()


async def test_no_session_tenant_context_sees_nothing(migrated_db: str) -> None:
    """Fail closed: if the app forgets to set app.current_tenant_id, RLS
    must deny all rows rather than defaulting to permissive (docs/security.md §4)."""
    app_engine = create_async_engine(_as_app_role(migrated_db))

    async with app_engine.connect() as conn:
        result = await conn.execute(text("SELECT * FROM admin_agents"))
        rows = result.fetchall()

    assert rows == []
    await app_engine.dispose()
