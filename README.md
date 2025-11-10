# FastAPI JWT API (Authlib, Postgres, psycopg)

Implementación de una API con FastAPI y autenticación basada en JWT usando Authlib. Incluye access tokens de corta duración (15 minutos), refresh tokens (7 días) con rotación y persistidos en PostgreSQL, middleware de validación, rate limiting en endpoints sensibles, CORS, cabeceras de seguridad, y limpieza perezosa (lazy cleanup) de tokens expirados.


## Características principales
- JWT con Authlib (HS256 por defecto).
- Access token: 15 minutos.
- Refresh token: 7 días. Rotación en cada refresh; revocación idempotente.
- Persistencia de refresh tokens en PostgreSQL (driver `psycopg`), almacenando solo el hash (SHA-256) del token.
- Middleware JWT que valida tokens en rutas protegidas.
- Middleware CORS para entorno local.
- Middleware de rate limiting en memoria (5 req/60s) para `/auth/login` y `/auth/refresh`.
- Cabeceras de seguridad en respuestas.
- Lazy cleanup de tokens expirados tras llamadas de auth (con baja probabilidad y lote limitado).


## Estructura del proyecto (resumen)
```
src/
  auth.py               # emisión/validación de JWT con Authlib
  db.py                 # conexión Postgres (psycopg) y SessionLocal
  middleware.py         # JWT middleware + cabeceras de seguridad
  models.py             # modelo RefreshToken (token_hash, jti, subject, ...)
  rate_limiter.py       # middleware de rate limiting en memoria
  routes_auth.py        # endpoints de login, refresh, revoke + lazy cleanup
  main.py               # configuración FastAPI, CORS, middlewares, routers
  libs/
    fake_login.py       # autenticación fake de ejemplo
  .env                  # variables de entorno de ejemplo (LOCAL, no producción)
```


## Requisitos
- Python 3.10+
- PostgreSQL accesible (credenciales en variables de entorno)

Dependencias principales:
```
pip install fastapi uvicorn[standard] python-dotenv sqlalchemy authlib psycopg[binary]
```


## Configuración (.env de ejemplo para desarrollo local)
El fichero `src/.env` se carga automáticamente desde `main.py` con `load_dotenv("src/.env")`. No usar en producción.

Variables relevantes:
- APP_NAME=api
- JWT_SECRET=dev_super_secret_key_with_minimum_32_chars_length_1234
- JWT_ISSUER=fastapi-example
- JWT_AUDIENCE=fastapi-clients
- ACCESS_TTL_MIN=15
- REFRESH_TTL_DAYS=7
- JWT_CLOCK_SKEW=5
- PSQL_USER=postgres
- PSQL_PASSWORD=postgres
- PSQL_HOST=localhost
- PSQL_PORT=5432
- PSQL_DB=fastapijwt
- LAZY_CLEANUP_PROB=0.05
- LAZY_CLEANUP_LIMIT=200

Notas:
- `JWT_SECRET` debe tener al menos 32 caracteres. En producción, usar un gestor de secretos y no el `.env`.
- Cambiar `JWT_ISSUER` y `JWT_AUDIENCE` a valores propios.


## Ejecución
```
uvicorn src.main:app --reload
```

UI de documentación:
- http://localhost:8000/docs


## Endpoints
- POST /auth/login
  - Body: { "username": "test", "password": "..." }
  - Retorna: { access_token, refresh_token, token_type=bearer, expires_in }
  - Aplica rate limiting (5 req/60s por IP)

- POST /auth/refresh
  - Body: { "refresh_token": "..." }
  - Emite nuevo access token y rota el refresh token (revoca el anterior).
  - Aplica rate limiting (5 req/60s por IP)

- POST /auth/revoke
  - Body: { "refresh_token": "..." }
  - Revoca el refresh token (idempotente).

- GET /protected
  - Requiere Authorization: Bearer <access_token>


## Seguridad y mejores prácticas aplicadas
- Validación estricta de JWT (Authlib): iss/aud obligatorios, exp/nbf/iat/jti/sub, leeway pequeño.
- Rechazo de secretos débiles: `JWT_SECRET` mínimo 32 chars.
- Middleware JWT añade cabeceras de seguridad:
  - X-Content-Type-Options: nosniff
  - X-Frame-Options: DENY
  - X-XSS-Protection: 1; mode=block
  - Referrer-Policy: no-referrer
  - Cache-Control: no-store
- Persistencia segura: se almacena `token_hash` (sha256) de los refresh tokens en DB.
- Comparación con `hmac.compare_digest` para evitar timing attacks.
- Rotación de refresh tokens: en cada refresh, se revoca el anterior y se guarda uno nuevo.
- Rate limiting en endpoints sensibles: `/auth/login` y `/auth/refresh`.
- CORS limitado a localhost para desarrollo (en producción, restringir a dominios exactos).


## Limpieza de tokens expirados
- Lazy cleanup: 
  - Al final de login/refresh/revoke, con probabilidad LAZY_CLEANUP_PROB (por defecto 5%), se elimina un lote de hasta LAZY_CLEANUP_LIMIT (por defecto 200) tokens expirados.
  - Es silencioso y no interrumpe el flujo.
- Job programado recomendado (producción):
  - Ejecutar un CronJob (Kubernetes, ECS, etc.) cada 15-60 minutos que haga:
    - DELETE FROM refresh_tokens WHERE expires_at < NOW();
  - Evita que múltiples réplicas ejecuten limpieza simultáneamente.


## Diagrama de arquitectura (Mermaid)
```mermaid
flowchart TD
  subgraph Client
    A[Cliente / Consumidor API]
  end

  subgraph API[FastAPI App]
    direction TB
    M1[CORS Middleware]
    M2[RateLimiter Middleware (5 req por 60s en login/refresh)]
    M3[JWTAuth Middleware]

    R1[/auth/login (POST -> TokenPair)/]
    R2[/auth/refresh (POST -> TokenPair)/]
    R3[/auth/revoke (POST -> {status: ok})/]
    R4[/protected (GET -> data)/]

    S1[AuthLib JWT]
    S2[Security Config]

    DBL[DB Layer (SQLAlchemy Session)]
    MDL[(Modelo: RefreshToken)]
  end

  subgraph DB[(PostgreSQL - psycopg)]
    TBL[(Tabla refresh_tokens)]
  end

  A -->|HTTP(S)| M1
  M1 --> M2 --> M3 --> API_CORE

  subgraph API_CORE[FastAPI Routers]
    direction TB
    RouterAuth[Router /auth]
    RouterAuth --> R1
    RouterAuth --> R2
    RouterAuth --> R3
    Other[Rutas protegidas] --> R4
  end

  R1 -->|valida credenciales| S1
  R1 -->|genera tokens| S1
  R1 -->|persistencia token_hash| DBL --> MDL --> TBL

  R2 -->|valida refresh JWT| S1
  R2 -->|verifica jti y token_hash| DBL --> MDL --> TBL
  R2 -->|rota refresh y revoca anterior| DBL --> MDL --> TBL
  R2 -->|genera access| S1

  R3 -->|valida refresh JWT| S1
  R3 -->|verifica jti y token_hash y revoca| DBL --> MDL --> TBL

  R4 -->|JWT access válido| M3

  S2 --> S1
  S2 --> M3

  subgraph Ops[Operación]
    direction TB
    ENV[.env local (APP_NAME, JWT_*, PSQL_*, LAZY_*)]
    CleanupJob[Cron/Job Limpieza de tokens expirados]
  end

  ENV -.-> API
  CleanupJob -.-> DB
```


## Notas de producción
- Habilitar HTTPS con HSTS desde el reverse proxy.
- Restringir CORS a orígenes específicos.
- Gestionar secretos con gestor de secretos (Vault, KeyVault, Secrets Manager).
- Añadir rate limiting adicional y/o WAF en el perímetro.
- Tarea de limpieza programada externa fiable.
- Monitorizar y auditar eventos relevantes (sin loggear tokens).


## Hallazgos de revisión y correcciones recomendadas
A continuación se listan los issues detectados durante la revisión y las correcciones/pautas recomendadas.

Alta prioridad
1) Creación de tablas en import time en varios módulos
- Problema: `Base.metadata.create_all(_engine)` se ejecuta en `routes_auth.py` y `main.py`.
- Impacto: efectos colaterales y fragilidad.
- Acción: centralizar la creación de tablas (idealmente en `main.py`) o usar migraciones (Alembic) para producción.

Media prioridad
2) Logging mínimo en lazy cleanup
- Problema: `_lazy_cleanup` silencia errores.
- Acción: registrar a nivel DEBUG/INFO cuando se eliminen filas y cuando ocurra un error (sin detener el flujo principal).

3) Longitud de `token_hash`
- Observación: `String(128)` para SHA-256 hex (64).
- Acción: opcionalmente cambiar a `String(64)` para limitar estrictamente.

Mejoras/operativas
4) En producción exigir `JWT_ISSUER` y `JWT_AUDIENCE` explícitos
- Acción: si `ENV=prod`, validar presencia sin valores por defecto.

5) /docs en producción (INTERNET)
- Acción: deshabilitar o proteger `/docs`, `/redoc`, `/openapi`.

6) Tamaño de payload
- Acción: limitar tamaño desde reverse proxy/gateway para defensa en profundidad.



## Licencia
Apache 2.0
