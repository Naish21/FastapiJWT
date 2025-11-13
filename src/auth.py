import os
import uuid
from datetime import datetime, timedelta, timezone

from authlib.jose import jwt, JoseError
from fastapi import HTTPException, status

# Load settings strictly from environment (no insecure defaults)
JWT_ISSUER = os.getenv("JWT_ISSUER", "fastapi-example")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "fastapi-clients")
JWT_ALG = os.getenv("JWT_ALG", "RS256")
ACCESS_TTL_MIN = int(os.getenv("ACCESS_TTL_MIN", "15"))
REFRESH_TTL_DAYS = int(os.getenv("REFRESH_TTL_DAYS", "7"))
CLOCK_SKEW_SECS = int(os.getenv("JWT_CLOCK_SKEW", "5"))  # small allowable clock skew

# Asymmetric keys (PEM). In RS256 mode, private key is required for signing and
# public key for verification. Fail fast if missing.
JWT_PRIVATE_KEY = os.getenv("JWT_PRIVATE_KEY")
JWT_PUBLIC_KEY = os.getenv("JWT_PUBLIC_KEY")


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


def _permissions_for_user(user: str) -> list[str]:
    """Return permissions embedded into JWT based on the username.
    - test1: only end1
    - test2: only end2
    - test: can access both end1 and end2
    Others: none
    """
    u = user.lower()
    if u == "test":
        return ["end1", "end2"]
    if u == "test1":
        return ["end1"]
    if u == "test2":
        return ["end2"]
    return []


def encode_access_token(subject: str) -> str:
    if JWT_ALG.startswith("RS"):
        if not JWT_PRIVATE_KEY:
            raise HTTPException(status_code=500, detail="JWT private key not configured")
        signing_key = JWT_PRIVATE_KEY
    else:
        # HS fallback only if explicitly configured
        secret = os.getenv("JWT_SECRET")
        if not secret or len(secret) < 32:
            raise HTTPException(status_code=500, detail="JWT secret not properly configured")
        signing_key = secret

    issued = now_utc()
    claims = _base_claims(
        subject, "access", issued, issued + timedelta(minutes=ACCESS_TTL_MIN)
    )
    # embed permissions
    claims["perms"] = _permissions_for_user(subject)
    return jwt.encode({"alg": JWT_ALG}, claims, signing_key).decode()


def encode_refresh_token(subject: str) -> tuple[str, dict]:
    if JWT_ALG.startswith("RS"):
        if not JWT_PRIVATE_KEY:
            raise HTTPException(status_code=500, detail="JWT private key not configured")
        signing_key = JWT_PRIVATE_KEY
    else:
        secret = os.getenv("JWT_SECRET")
        if not secret or len(secret) < 32:
            raise HTTPException(status_code=500, detail="JWT secret not properly configured")
        signing_key = secret

    issued = now_utc()
    claims = _base_claims(
        subject, "refresh", issued, issued + timedelta(days=REFRESH_TTL_DAYS)
    )
    # embed same permissions also in refresh (useful for rotation policies)
    claims["perms"] = _permissions_for_user(subject)
    token = jwt.encode({"alg": JWT_ALG}, claims, signing_key).decode()
    return token, claims


def decode_token(token: str) -> dict:
    if JWT_ALG.startswith("RS"):
        verify_key = JWT_PUBLIC_KEY
        if not verify_key:
            raise HTTPException(status_code=500, detail="JWT public key not configured")
    else:
        secret = os.getenv("JWT_SECRET")
        if not secret or len(secret) < 32:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid server configuration",
            )
        verify_key = secret

    try:
        claims = jwt.decode(
            token,
            verify_key,
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
