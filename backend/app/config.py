from functools import lru_cache
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_MARKERS = ("docuciv_app:docuciv_app", "docuciv_owner:docuciv_owner", "localhost")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DOCUCIV_", env_file=".env", extra="ignore")

    environment: Literal["dev", "staging", "production"] = "dev"
    # Rôle applicatif: non-superuser, soumis à la RLS (jamais le rôle de migration).
    database_url: str = "postgresql+asyncpg://docuciv_app:docuciv_app@localhost:5432/docuciv"
    # Rôle propriétaire du schéma, utilisé uniquement par Alembic.
    migration_database_url: str = (
        "postgresql+asyncpg://docuciv_owner:docuciv_owner@localhost:5432/docuciv"
    )
    redis_url: str = "redis://localhost:6379/0"
    # Tarif provisoire (FCFA) en attendant la configuration par tenant/type (concept.md §4).
    default_amount_due_fcfa: int = 1000

    @model_validator(mode="after")
    def _no_dev_defaults_outside_dev(self) -> Self:
        """Fail closed: staging/production refusent de démarrer avec les valeurs de dev.

        Les secrets viennent de Vault/Secrets Manager injectés en variables d'environnement,
        jamais du dépôt (docs/security.md §10).
        """
        if self.environment == "dev":
            return self
        for name in ("database_url", "migration_database_url", "redis_url"):
            value = getattr(self, name)
            if any(marker in value for marker in _DEV_MARKERS):
                raise ValueError(
                    f"{name} utilise une valeur de dev en environnement {self.environment}"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
