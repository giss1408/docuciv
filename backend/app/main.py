from fastapi import FastAPI

from app.core.logging import configure_logging

configure_logging()

app = FastAPI(title="DocuCiv API", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
