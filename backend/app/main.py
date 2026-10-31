from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.body_limit import MaxBodySizeMiddleware
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.security_headers import SecurityHeadersMiddleware

configure_logging()

# Interactive API docs are a Phase-0 developer convenience, never exposed in
# production (docs/security.md §2 "Security misconfiguration").
_docs_enabled = not settings.is_production

app = FastAPI(
    title="DocuCiv API",
    version="0.1.0",
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(MaxBodySizeMiddleware)

# No origin is trusted by default; staging/production must set
# DOCUCIV_CORS_ALLOWED_ORIGINS explicitly (enforced in app.core.config).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
