from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DOCUCIV_", env_file=".env", extra="ignore")

    environment: str = "dev"
    # Rôle applicatif: non-superuser, soumis à la RLS (jamais le rôle de migration).
    database_url: str = "postgresql+asyncpg://docuciv_app:docuciv_app@localhost:5432/docuciv"
    # Rôle propriétaire du schéma, utilisé uniquement par Alembic.
    migration_database_url: str = (
        "postgresql+asyncpg://docuciv_owner:docuciv_owner@localhost:5432/docuciv"
    )
    redis_url: str = "redis://localhost:6379/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
