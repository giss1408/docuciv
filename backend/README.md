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

## Multi-tenancy

Every business table carries `tenant_id` and is protected by a PostgreSQL RLS policy (see `alembic/versions/0001_initial_schema_and_rls.py` for the reference pattern). The app sets `app.current_tenant_id` per request via `app.db.session.tenant_session`; the Owner role bypasses RLS through a dedicated DB role and must log every cross-tenant access to `PlatformAuditLog`.
