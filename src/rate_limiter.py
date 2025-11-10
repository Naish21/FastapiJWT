import time
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimiterMiddleware(BaseHTTPMiddleware):
    def __init__(
        self, app, endpoints: list[str], window_seconds: int = 60, max_requests: int = 5
    ):
        super().__init__(app)
        self.endpoints = endpoints
        self.window = window_seconds
        self.max_requests = max_requests
        self._store: dict[tuple[str, str], list[float]] = {}

    async def dispatch(self, request: Request, call_next: Callable):
        path = request.url.path
        if any(path.endswith(ep) or path.startswith(ep) for ep in self.endpoints):
            client_ip = request.client.host if request.client else "anonymous"
            key = (client_ip, path)
            now = time.time()
            bucket = self._store.get(key, [])
            # prune old entries
            bucket = [ts for ts in bucket if now - ts < self.window]
            if len(bucket) >= self.max_requests:
                retry_after = (
                    int(self.window - (now - bucket[0])) if bucket else self.window
                )
                resp = JSONResponse(
                    status_code=429, content={"detail": "Too Many Requests"}
                )
                resp.headers["Retry-After"] = str(max(1, retry_after))
                resp.headers["X-RateLimit-Limit"] = str(self.max_requests)
                resp.headers["X-RateLimit-Remaining"] = "0"
                return resp
            bucket.append(now)
            self._store[key] = bucket
            response = await call_next(request)
            remaining = max(0, self.max_requests - len(bucket))
            response.headers["X-RateLimit-Limit"] = str(self.max_requests)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            return response
        return await call_next(request)
