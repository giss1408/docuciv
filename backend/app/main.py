from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.demo import router as demo_router
from app.logging import configure_logging
from app.routers import evidence, issuer, outbox, reclamations, requests


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="DocuCiv API", version="0.1.0")

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    origins = get_settings().cors_origins
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
        )

    app.include_router(demo_router)
    app.include_router(requests.router)
    app.include_router(evidence.router)
    app.include_router(issuer.router)
    app.include_router(reclamations.router)
    app.include_router(outbox.router)
    return app


app = create_app()
