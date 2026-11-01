import uuid
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


@asynccontextmanager
async def _scoped_session(**context: uuid.UUID) -> AsyncIterator[AsyncSession]:
    """Session transactionnelle portant le contexte RLS (`app.<clé>`).

    set_config(..., is_local=true): la valeur disparaît à la fin de la transaction, donc elle ne
    fuit jamais vers une autre requête du pool. Les policies PostgreSQL filtrent sur ces valeurs
    (docs/data-model.md §4).
    """
    get_engine()
    assert _sessionmaker is not None
    async with _sessionmaker() as session, session.begin():
        for key, value in context.items():
            await session.execute(
                text("SELECT set_config(:k, :v, true)"), {"k": f"app.{key}", "v": str(value)}
            )
        yield session


def tenant_session(tenant_id: uuid.UUID) -> AbstractAsyncContextManager[AsyncSession]:
    """Contexte d'un agent d'administration (tenant)."""
    return _scoped_session(tenant_id=tenant_id)


def user_session(user_id: uuid.UUID) -> AbstractAsyncContextManager[AsyncSession]:
    """Contexte d'un citoyen/entreprise: ne voit que ses propres lignes."""
    return _scoped_session(user_id=user_id)
