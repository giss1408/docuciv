import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings

BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def migrated_db() -> None:
    """Smoke tests DB: activés par DOCUCIV_TEST_DB=1 (docker compose up -d postgres)."""
    if os.environ.get("DOCUCIV_TEST_DB") != "1":
        pytest.skip("DOCUCIV_TEST_DB=1 requis (docker compose up -d postgres)")
    subprocess.run([sys.executable, "-m", "alembic", "downgrade", "base"], cwd=BACKEND, check=True)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True)


@pytest.fixture(autouse=True)
async def _reset_engine():
    import app.db as db

    yield
    if db._engine is not None:
        await db._engine.dispose()
    db._engine = None
    db._sessionmaker = None


@pytest.fixture
def new_tenant_id() -> uuid.UUID:
    return uuid.uuid4()


async def owner_exec(sql: str) -> None:
    engine = create_async_engine(get_settings().migration_database_url)
    async with engine.begin() as conn:
        await conn.execute(text(sql))
    await engine.dispose()
