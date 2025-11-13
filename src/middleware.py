import os
from typing import Callable, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .auth import decode_token


class JWTAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, public_paths: Optional[list[str]] = None):
        super().__init__(app)
        self.public_paths = public_paths or []
        self.public_key = os.environ.get("JWT_PUBLIC_KEY")
        self.alg = os.environ.get("JWT_ALG", "RS256")
        if self.alg.startswith("RS"):
            if not self.public_key:
                raise RuntimeError("JWT_PUBLIC_KEY must be set when using RS256")
        else:
            # HS fallback only when explicitly configured
            self.secret = os.environ.get("JWT_SECRET")
            if not self.secret or len(self.secret) < 32:
                raise RuntimeError("JWT_SECRET must be set and at least 32 characters")

    async def dispatch(self, request: Request, call_next: Callable):
        # Security headers
        request.state.start_time = None
        response = None
        path = request.url.path
        # Allow only explicitly configured public paths
        if any(path.startswith(p) for p in self.public_paths):
            response = await call_next(request)
        else:
            auth = request.headers.get("Authorization")
            if not auth or not auth.lower().startswith("bearer "):
                return JSONResponse({"detail": "Missing bearer token"}, status_code=401)
            token = auth.split(" ", 1)[1]
            try:
                claims = decode_token(token)
                if claims.get("type") != "access":
                    return JSONResponse(
                        {"detail": "Invalid token type"}, status_code=401
                    )
                request.state.jwt = claims
            except Exception:
                return JSONResponse({"detail": "Invalid token"}, status_code=401)
            response = await call_next(request)

        # Add basic security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response
