import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import RedirectResponse

from .db import _engine
from .middleware import JWTAuthMiddleware
from .models import Base
from .rate_limiter import RateLimiterMiddleware
from .routes_auth import router as auth_router

VERSION = "0.1.0"

load_dotenv("src/.env")

DESCRIPTION = """
Fastapi example to see how to implement JWT
"""

app_name = os.environ.get("APP_NAME")
URL_PREFIX = f"/{app_name}" if app_name is not None else ""


app = FastAPI(
    title="Example JWT Implementation",
    docs_url=f"{URL_PREFIX}/docs",
    redoc_url=f"{URL_PREFIX}/redoc",
    openapi_url=f"{URL_PREFIX}/openapi.json",
    description=DESCRIPTION,
    version=VERSION,
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
)


@app.get(f"{URL_PREFIX}/", include_in_schema=False)
async def status():
    """Devuelve OK si la API está funcionando"""
    return RedirectResponse("/docs")


# Initialize DB models
Base.metadata.create_all(_engine)

# Mount auth routes
app.include_router(auth_router, prefix=URL_PREFIX)

# CORS middleware (restringe orígenes en prod; aquí ejemplo para local dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://127.0.0.1"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)

# Rate limit middleware for sensitive endpoints
login_ep = f"{URL_PREFIX}/auth/login"
refresh_ep = f"{URL_PREFIX}/auth/refresh"
app.add_middleware(
    RateLimiterMiddleware,
    endpoints=[login_ep, refresh_ep],
    window_seconds=60,
    max_requests=5,
)

# Attach JWT middleware; make only /auth public (docs y openapi quedan protegidos)
app.add_middleware(
    JWTAuthMiddleware,
    public_paths=[f"{URL_PREFIX}/auth"],
)

# Logging básico
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("app")


@app.get(f"{URL_PREFIX}/protected")
async def protected():
    return {"message": "secure data"}


# OpenAPI dinámico filtrado por permisos
@app.get(f"{URL_PREFIX}/openapi.json", include_in_schema=False)
async def filtered_openapi(request: Request):
    claims = getattr(request.state, "jwt", None)
    if not claims:
        raise HTTPException(status_code=401, detail="Missing token")
    perms = set((claims.get("perms") or []))

    # Esquema completo
    full_schema = app.openapi()
    # Clonar shallow
    schema = {**full_schema, "paths": {}}

    # Paths siempre visibles (auth)
    always_keep = {
        f"{URL_PREFIX}/auth/login",
        f"{URL_PREFIX}/auth/refresh",
        f"{URL_PREFIX}/auth/revoke",
        f"{URL_PREFIX}/protected",  # opcional mantener para pruebas generales
    }

    # Reglas por permisos
    allowed_by_perm = set(always_keep)
    if "end1" in perms:
        allowed_by_perm.add(f"{URL_PREFIX}/end1")
    if "end2" in perms:
        allowed_by_perm.add(f"{URL_PREFIX}/end2")

    # Usuario "test" puede ver ambos; la regla anterior ya cubre si tiene ambos perms

    # Filtrar paths
    for path, item in full_schema.get("paths", {}).items():
        if path in allowed_by_perm:
            schema["paths"][path] = item

    return JSONResponse(schema)


def _require_perm(request, perm: str):
    claims = getattr(request.state, "jwt", None)
    if not claims:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Missing token")
    perms = claims.get("perms") or []
    if perm not in perms:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Forbidden")


@app.get(f"{URL_PREFIX}/end1")
async def end1(request):
    _require_perm(request, "end1")
    return {"message": "end1 data"}


@app.get(f"{URL_PREFIX}/end2")
async def end2(request):
    _require_perm(request, "end2")
    return {"message": "end2 data"}
