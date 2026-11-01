from fastapi import FastAPI

from app.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="DocuCiv API", version="0.1.0")

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
