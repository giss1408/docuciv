from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_security_headers_present_on_response() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "max-age" in response.headers["strict-transport-security"]


async def test_docs_disabled_in_production(monkeypatch) -> None:
    """docs/security.md §2 — no interactive API docs exposed in production."""
    import importlib

    from app.core import config

    monkeypatch.setenv("DOCUCIV_ENVIRONMENT", "production")
    monkeypatch.setenv("DOCUCIV_SECRET_KEY", "a-real-secret-from-vault-aaaaaaaaaaaaaaaaaaaa")
    monkeypatch.setenv("DOCUCIV_CORS_ALLOWED_ORIGINS", '["https://admin.docuciv.ci"]')
    importlib.reload(config)
    assert config.Settings().is_production is True


async def test_oversized_body_rejected() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"content-length": str(50 * 1024 * 1024)}
        response = await client.get("/health", headers=headers)
    assert response.status_code == 413
