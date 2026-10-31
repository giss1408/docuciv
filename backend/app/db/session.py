from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def tenant_session(tenant_id: UUID | None) -> AsyncGenerator[AsyncSession, None]:
    """Yields a session with the PostgreSQL RLS session variable set for this request.

    tenant_id is None only for the Owner role, which bypasses tenant RLS policies
    via a dedicated DB role (see docs/security.md §2/§4) — never via an app-level skip.
    """
    async with SessionLocal() as session:
        if tenant_id is not None:
            await session.execute(
                text("SELECT set_config('app.current_tenant_id', :tid, false)"),
                {"tid": str(tenant_id)},
            )
        yield session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
