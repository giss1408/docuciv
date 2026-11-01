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
    # Stockage S3-compatible (MinIO en dev). SSE-KMS activé si s3_kms_key_id est renseigné.
    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_bucket: str = "docuciv-dev"
    s3_region: str = "us-east-1"
    s3_access_key_id: str = "minioadmin"
    s3_secret_access_key: str = "minioadmin"
    s3_kms_key_id: str | None = None
    evidence_max_bytes: int = 10 * 1024 * 1024
    evidence_max_pixels: int = 40_000_000
    evidence_max_per_request: int = 5
    upload_url_ttl_seconds: int = 300
    evidence_view_ttl_seconds: int = 120
    # Délai de traitement si le tenant n'a pas de configuration pour ce type (notifications.md §4).
    default_processing_business_days: int = 5
    # ClamAV (clamd). `disabled` n'est toléré qu'en dev: jamais de contournement silencieux.
    antivirus: Literal["clamav", "disabled"] = "disabled"
    clamd_host: str = "localhost"
    clamd_port: int = 3310
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
        if self.s3_secret_access_key == "minioadmin" or self.antivirus == "disabled":
            raise ValueError("stockage/antivirus de dev interdits hors environnement dev")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
