"""Smoke tests de la connexion jetable de démonstration."""

import pytest
from test_issuer import client

from app.config import Settings, get_settings
from app.demo import Claims, make_token, read_token
from app.main import app

SECRET = "s" * 40
CODE = "demo-code-2026"


def demo_settings(**kw: object) -> Settings:
    return Settings(demo_mode=True, demo_access_code=CODE, demo_token_secret=SECRET, **kw)  # type: ignore[arg-type]


@pytest.fixture
def demo():  # type: ignore[no-untyped-def]
    app.dependency_overrides[get_settings] = lambda: demo_settings()
    yield
    app.dependency_overrides.clear()


async def login(role: str, code: str = CODE):  # type: ignore[no-untyped-def]
    async with client() as c:
        return await c.post("/demo/login", json={"role": role, "access_code": code})


# --- sans base de données ------------------------------------------------------------------


def test_demo_mode_requires_strong_secrets_and_never_production() -> None:
    with pytest.raises(ValueError):
        Settings(demo_mode=True)
    with pytest.raises(ValueError):
        Settings(demo_mode=True, demo_access_code="short", demo_token_secret=SECRET)
    with pytest.raises(ValueError):
        Settings(
            environment="production",
            demo_mode=True,
            demo_access_code=CODE,
            demo_token_secret=SECRET,
        )


def test_token_roundtrip_tamper_and_expiry() -> None:
    s = demo_settings()
    import uuid

    claims = Claims("agent", uuid.uuid4(), uuid.uuid4())
    token, exp = make_token(s, claims, now=1_000_000)
    assert read_token(s, token, now=1_000_001) == claims
    assert read_token(s, token, now=exp + 1) is None  # expiré
    body, sig = token.split(".")
    assert read_token(s, body + "." + sig[:-2] + "AA", now=1_000_001) is None  # signature
    forged = make_token(demo_settings(), Claims("citizen", claims.user_id, None), now=1_000_000)
    assert read_token(s, forged[0].split(".")[0] + "." + sig, now=1_000_001) is None  # corps changé
    assert read_token(s, "garbage") is None
    other = Settings(demo_mode=True, demo_access_code=CODE, demo_token_secret="o" * 40)
    assert read_token(other, token, now=1_000_001) is None  # autre secret
    assert read_token(Settings(), token) is None  # démo désactivée


async def test_login_hidden_when_demo_mode_off() -> None:
    assert (await login("citizen")).status_code == 404


# --- avec base de données ------------------------------------------------------------------


@pytest.mark.usefixtures("migrated_db", "demo")
async def test_login_and_tokens_open_the_right_doors() -> None:
    assert (await login("citizen", "wrong-code")).status_code == 403

    citizen = (await login("citizen")).json()["token"]
    agent = (await login("agent")).json()["token"]  # idempotent: re-seed sans erreur
    assert (await login("agent")).status_code == 200
    ch, ah = {"Authorization": f"Bearer {citizen}"}, {"Authorization": f"Bearer {agent}"}

    async with client() as c:
        assert (await c.get("/reclamations", headers=ch)).status_code == 200
        assert (await c.get("/issuer/outbox", headers=ah)).status_code == 200
        # Un jeton ne donne jamais l'autre rôle.
        assert (await c.get("/issuer/outbox", headers=ch)).status_code == 401
        assert (await c.get("/reclamations", headers=ah)).status_code == 401
        # Jeton falsifié ou absent.
        bad = {"Authorization": f"Bearer {citizen[:-3]}abc"}
        assert (await c.get("/reclamations", headers=bad)).status_code == 401
        assert (await c.get("/reclamations")).status_code == 401
