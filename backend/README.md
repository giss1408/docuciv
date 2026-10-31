# DocuCiv Backend

FastAPI backend, multi-tenant via PostgreSQL Row-Level Security. See `/docs` at the repo root for specs (architecture, data model, security, API).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
docker compose up -d postgres redis
alembic upgrade head
```

## Run

```bash
uvicorn app.main:app --reload
```

## Tests

Smoke tests only during feature work (fast, no external deps) — see `docs/workflow.md` §1. e2e suite runs at end of phase / on `integration`.

```bash
pytest
ruff check app tests
mypy app
```

The BOLA/RLS isolation test (`tests/test_rls_isolation.py`) needs a real PostgreSQL instance and is skipped unless `DOCUCIV_TEST_DATABASE_URL` is set:

```bash
docker run -d --name docuciv-test-pg -e POSTGRES_USER=docuciv -e POSTGRES_PASSWORD=docuciv \
  -e POSTGRES_DB=docuciv_test -p 55432:5432 postgres:16
DOCUCIV_TEST_DATABASE_URL=postgresql+asyncpg://docuciv:docuciv@localhost:55432/docuciv_test pytest tests/test_rls_isolation.py
```

This is also wired into CI (`.github/workflows/backend-ci.yml`) against the `postgres` service container, so it runs on every PR — not just at phase end — because it's a per-endpoint merge gate (AGENTS.md règle 8), not a full user-journey e2e test.

## Multi-tenancy & security hardening

- Every business table carries `tenant_id` and is protected by a PostgreSQL RLS policy (see `alembic/versions/0001_initial_schema_and_rls.py` for the reference pattern).
- **The application must connect as `docuciv_app`** (created in `alembic/versions/0002_app_and_owner_db_roles.py`), never as a superuser or the table owner — PostgreSQL superusers/owners bypass RLS unconditionally even with `FORCE ROW LEVEL SECURITY`. This was caught by `tests/test_rls_isolation.py` while writing it: the migration role is a superuser and silently saw every tenant's rows.
- The app sets `app.current_tenant_id` per request via `app.db.session.get_scoped_db` (bound to the authenticated `Principal`'s tenant, see `app/core/auth.py`).
- Owner cross-tenant access never reuses the tenant-scoped path: `app.core.owner_access.owner_db` runs on the separate `docuciv_owner` role (`BYPASSRLS`) and always writes a justified `PlatformAuditLog` entry before the query executes (docs/security.md §6).
- Baseline hardening wired into `app/main.py`: strict CORS (no origin trusted by default, enforced outside `dev` by `app/core/config.py`), security response headers (`app/core/security_headers.py`), request body size cap (`app/core/body_limit.py`), and interactive API docs (`/docs`, `/openapi.json`) disabled in production.
- PII never goes into logs in clear text — use `app.core.pii.hash_for_logs` for any correlation identifier (docs/security.md §7).
- Docker image runs as a non-root user (docs/security.md §10).

Real OIDC token issuance (Keycloak/Auth0-like) isn't wired up yet — `app/core/auth.py` implements the verification/RBAC *shape* every endpoint depends on (`require_role`, `get_scoped_db`), so no future endpoint can be added without going through it, but token issuance itself is Phase 2+ scope.
