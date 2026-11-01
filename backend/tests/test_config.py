import pytest
from pydantic import ValidationError

from app.config import Settings


def test_dev_defaults_allowed_in_dev() -> None:
    assert Settings(environment="dev").environment == "dev"


@pytest.mark.parametrize("env", ["staging", "production"])
def test_dev_defaults_rejected_outside_dev(env: str) -> None:
    with pytest.raises(ValidationError):
        Settings(environment=env)


def test_production_accepts_injected_secrets() -> None:
    s = Settings(
        environment="production",
        database_url="postgresql+asyncpg://app:s3cr3t@db.internal:5432/docuciv",
        migration_database_url="postgresql+asyncpg://own:s3cr3t@db.internal:5432/docuciv",
        redis_url="redis://:pw@cache.internal:6379/0",
    )
    assert s.environment == "production"


def test_unknown_environment_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="prod")  # type: ignore[arg-type]
