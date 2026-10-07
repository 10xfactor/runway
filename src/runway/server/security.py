"""Loopback-only hardening: Host check (DNS rebinding), per-session token, strict headers."""

from __future__ import annotations

import hmac
import secrets

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

CSP = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-src 'self'"


def new_token() -> str:
    return secrets.token_urlsafe(24)


class Guard(BaseHTTPMiddleware):
    def __init__(self, app: object, token: str, allowed_hosts: set[str]) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.token, self.allowed_hosts = token, allowed_hosts

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        host = request.headers.get("host", "").rsplit(":", 1)[0].strip("[]")
        if host not in self.allowed_hosts:
            return JSONResponse({"detail": "bad host"}, status_code=403)
        if request.url.path.startswith("/api/") and request.url.path != "/api/health":
            supplied = request.headers.get("authorization", "").removeprefix("Bearer ") or request.query_params.get(
                "token", ""
            )
            if not hmac.compare_digest(supplied, self.token):
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
        resp = await call_next(request)
        resp.headers["Content-Security-Policy"] = CSP
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp
