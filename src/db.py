import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Build Postgres URL from environment variables
# Expected env vars: PSQL_USER, PSQL_PASSWORD, PSQL_HOST, PSQL_PORT
PSQL_USER = os.getenv("PSQL_USER")
PSQL_PASSWORD = os.getenv("PSQL_PASSWORD")
PSQL_HOST = os.getenv("PSQL_HOST", "localhost")
PSQL_PORT = os.getenv("PSQL_PORT", "5432")
PSQL_DB = os.getenv("PSQL_DB", "fastapijwt")

if not PSQL_USER or not PSQL_PASSWORD:
    # Keep a clear error if credentials missing
    raise RuntimeError(
        "Missing required env vars PSQL_USER and/or PSQL_PASSWORD for Postgres connection"
    )

DB_URL = (
    f"postgresql+psycopg://{PSQL_USER}:{PSQL_PASSWORD}@{PSQL_HOST}:{PSQL_PORT}/{PSQL_DB}"
)

_engine = create_engine(DB_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
