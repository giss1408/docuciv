from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.auth import Principal, Role, get_current_principal
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


async def get_scoped_db(
    principal: Principal = Depends(get_current_principal),
) -> AsyncGenerator[AsyncSession, None]:
    """Request-scoped session bound to the caller's tenant via RLS.

    This is the dependency every tenant-facing endpoint must use instead of
    get_db — it makes BOLA structurally harder: even a forgotten `WHERE
    tenant_id = ...` still can't cross tenants, because PostgreSQL enforces
    it (docs/security.md §4). The Owner role never gets a free pass here —
    see app.core.owner_access for the explicit, audited cross-tenant path.
    """
    if principal.role is Role.owner:
        raise RuntimeError(
            "Owner principal must use app.core.owner_access.owner_db, never get_scoped_db "
            "(docs/security.md §4: Owner access must be an explicit, justified, audited path)"
        )
    async with tenant_session(principal.tenant_id) as session:
        yield session
