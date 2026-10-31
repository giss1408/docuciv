from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Rejects oversized request bodies before they reach a handler
    (docs/security.md §2 "Unrestricted resource consumption"). Evidence
    uploads never go through this API — they go direct-to-S3 via a
    pre-signed URL (AGENTS.md règle 12) — so a small ceiling is safe here.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None and int(content_length) > settings.max_request_body_bytes:
            return JSONResponse(status_code=413, content={"detail": "Request body too large"})
        return await call_next(request)
