from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline security headers for every response (docs/security.md §2
    "Security misconfiguration", §8 CSP for the Flutter Web admin apps).

    This API itself serves no HTML, so CSP here is defense-in-depth only —
    the Admin Portal/Owner Backoffice (Flutter Web) must set their own CSP
    at the hosting layer (static web server / CDN), see docs/security.md §8.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'")
        return response
