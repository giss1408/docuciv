from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# >= 32 bytes so HS256 (RFC 7518 §3.2) doesn't warn even in dev.
_INSECURE_DEFAULT_SECRET = "change-me-in-vault-aaaaaaaaaaaaaaaaaaaa"  # noqa: S105 — sentinel, not a real secret


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DOCUCIV_")

    environment: str = "dev"
    database_url: str = "postgresql+asyncpg://docuciv:docuciv@localhost:5432/docuciv"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = _INSECURE_DEFAULT_SECRET
    log_level: str = "INFO"

    # CORS: no origin is trusted by default — staging/production must set this
    # explicitly (docs/security.md §2 "Security misconfiguration").
    cors_allowed_origins: list[str] = []

    # Rate limiting (Redis-backed, docs/security.md §1 DoS / §2 resource consumption).
    rate_limit_default_per_minute: int = 60
    rate_limit_verify_per_minute: int = 20

    # Max request body size in bytes (10 MiB) — resource consumption guard for
    # non-upload endpoints; evidence uploads go direct-to-S3, never through
    # this API (AGENTS.md règle 12, docs/security.md §2bis).
    max_request_body_bytes: int = 10 * 1024 * 1024

    @field_validator("environment")
    @classmethod
    def _validate_environment(cls, v: str) -> str:
        allowed = {"dev", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}, got {v!r}")
        return v

    @model_validator(mode="after")
    def _forbid_insecure_defaults_outside_dev(self) -> "Settings":
        if self.environment != "dev" and self.secret_key == _INSECURE_DEFAULT_SECRET:
            raise ValueError(
                "DOCUCIV_SECRET_KEY must be set from Vault/Secrets Manager outside dev "
                "(docs/security.md §10) — refusing to boot with the placeholder default."
            )
        if self.environment != "dev" and not self.cors_allowed_origins:
            raise ValueError(
                "DOCUCIV_CORS_ALLOWED_ORIGINS must be set explicitly outside dev "
                "(docs/security.md §2 security misconfiguration) — no wildcard CORS."
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


settings = Settings()
