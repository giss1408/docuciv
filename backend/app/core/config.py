from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DOCUCIV_")

    environment: str = "dev"
    database_url: str = "postgresql+asyncpg://docuciv:docuciv@localhost:5432/docuciv"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me-in-vault"
    log_level: str = "INFO"


settings = Settings()
