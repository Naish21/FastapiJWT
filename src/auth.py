import os
import uuid
from datetime import datetime, timedelta, timezone

from authlib.jose import jwt, JoseError
from fastapi import HTTPException, status

# Load settings strictly from environment (no insecure defaults)
JWT_ISSUER = os.getenv("JWT_ISSUER", "fastapi-example")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "fastapi-clients")
JWT_ALG = os.getenv("JWT_ALG", "HS256")
ACCESS_TTL_MIN = int(os.getenv("ACCESS_TTL_MIN", "15"))
REFRESH_TTL_DAYS = int(os.getenv("REFRESH_TTL_DAYS", "7"))
CLOCK_SKEW_SECS = int(os.getenv("JWT_CLOCK_SKEW", "5"))  # small allowable clock skew


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _base_claims(subject: str, typ: str, issued: datetime, exp: datetime) -> dict:
    return {
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": int(issued.timestamp()),
        "nbf": int(issued.timestamp()) - CLOCK_SKEW_SECS,
        "exp": int(exp.timestamp()) + CLOCK_SKEW_SECS,
        "sub": subject,
        "type": typ,
        "jti": uuid.uuid4().hex,
    }


def encode_access_token(subject: str, secret: str) -> str:
    if not secret or len(secret) < 32:
        raise HTTPException(
            status_code=500, detail="JWT secret not properly configured"
        )
    issued = now_utc()
    claims = _base_claims(
        subject, "access", issued, issued + timedelta(minutes=ACCESS_TTL_MIN)
    )
    return jwt.encode({"alg": JWT_ALG}, claims, secret).decode()


def encode_refresh_token(subject: str, secret: str) -> tuple[str, dict]:
    if not secret or len(secret) < 32:
        raise HTTPException(
            status_code=500, detail="JWT secret not properly configured"
        )
    issued = now_utc()
    claims = _base_claims(
        subject, "refresh", issued, issued + timedelta(days=REFRESH_TTL_DAYS)
    )
    token = jwt.encode({"alg": JWT_ALG}, claims, secret).decode()
    return token, claims


def decode_token(token: str, secret: str) -> dict:
    if not secret or len(secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid server configuration",
        )
    try:
        claims = jwt.decode(
            token,
            secret,
            claims_options={
                "iss": {"essential": True, "values": [JWT_ISSUER]},
                "aud": {"essential": True, "values": [JWT_AUDIENCE]},
                "exp": {"essential": True},
                "nbf": {"essential": True},
                "sub": {"essential": True},
                "jti": {"essential": True},
            },
        )
        claims.validate(leeway=CLOCK_SKEW_SECS)
        return dict(claims)
    except JoseError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
