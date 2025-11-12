import hashlib
import hmac
import os
import random
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .auth import (
    encode_access_token,
    encode_refresh_token,
    decode_token,
)
from .db import get_db
from .models import RefreshToken, Base

router = APIRouter(prefix="/auth", tags=["auth"])

# Lazy cleanup configuration
_LAZY_CLEANUP_PROB = float(os.getenv("LAZY_CLEANUP_PROB", "0.05"))  # 5% por invocación
_LAZY_CLEANUP_LIMIT = int(
    os.getenv("LAZY_CLEANUP_LIMIT", "200")
)  # máx. 200 filas por pasada


def _lazy_cleanup(db: Session) -> None:
    """Elimina un pequeño lote de refresh tokens expirados.
    Diseñado para ser cheap y no bloquear el camino crítico.
    """
    try:
        now = datetime.now(timezone.utc)
        # Ejecuta un delete limitado por lotes: SQLAlchemy Core/ORM no soporta LIMIT en delete
        # Por simplicidad, obtenemos IDs y luego delete por ID.
        expired_ids = [
            row.id
            for row in db.query(RefreshToken.id)
            .filter(RefreshToken.expires_at < now)
            .limit(_LAZY_CLEANUP_LIMIT)
            .all()
        ]
        if not expired_ids:
            return
        db.query(RefreshToken).filter(RefreshToken.id.in_(expired_ids)).delete(
            synchronize_session=False
        )
        db.commit()
    except Exception:
        # Silenciar errores para no afectar al flujo de autenticación
        db.rollback()
        return


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 15 * 60


class RefreshRequest(BaseModel):
    refresh_token: str


class RevokeRequest(BaseModel):
    refresh_token: str


@router.post("/login", response_model=TokenPair)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    # Replace with real authentication. Using fake_login for the demo
    from .libs.fake_login import login as fake_login

    if not fake_login(data.username, data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    access = encode_access_token(data.username)
    refresh_token, claims = encode_refresh_token(data.username)

    expires_at = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)

    db_obj = RefreshToken(
        jti=claims["jti"],
        subject=data.username,
        token_hash=hashlib.sha256(refresh_token.encode()).hexdigest(),
        issued_at=datetime.fromtimestamp(claims["iat"], tz=timezone.utc),
        expires_at=expires_at,
        revoked=False,
    )
    db.add(db_obj)
    db.commit()

    # Lazy cleanup con baja probabilidad
    if random.random() < _LAZY_CLEANUP_PROB:
        _lazy_cleanup(db)

    return TokenPair(access_token=access, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenPair)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    claims = decode_token(body.refresh_token)
    if claims.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    # Check existence and status in DB and verify token hash
    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()
    db_obj: Optional[RefreshToken] = (
        db.query(RefreshToken)
        .filter(RefreshToken.jti == claims["jti"], RefreshToken.revoked == False)
        .first()
    )
    if not db_obj or not hmac.compare_digest(db_obj.token_hash, token_hash):
        raise HTTPException(
            status_code=401, detail="Refresh token not found or revoked"
        )

    # Issue new access and optionally a rotated refresh token
    access = encode_access_token(claims["sub"])

    # For simplicity, rotate refresh tokens to reduce risk
    new_refresh_token, new_claims = encode_refresh_token(claims["sub"]) 

    # Revoke old and store new
    db_obj.revoked = True
    replacement = RefreshToken(
        jti=new_claims["jti"],
        subject=claims["sub"],
        token_hash=hashlib.sha256(new_refresh_token.encode()).hexdigest(),
        issued_at=datetime.fromtimestamp(new_claims["iat"], tz=timezone.utc),
        expires_at=datetime.fromtimestamp(new_claims["exp"], tz=timezone.utc),
        revoked=False,
    )
    db.add(replacement)
    db.commit()

    # Lazy cleanup con baja probabilidad
    if random.random() < _LAZY_CLEANUP_PROB:
        _lazy_cleanup(db)

    return TokenPair(access_token=access, refresh_token=new_refresh_token)


@router.post("/revoke")
def revoke(body: RevokeRequest, db: Session = Depends(get_db)):
    claims = decode_token(body.refresh_token)
    if claims.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()
    db_obj: Optional[RefreshToken] = (
        db.query(RefreshToken)
        .filter(RefreshToken.jti == claims["jti"], RefreshToken.revoked == False)
        .first()
    )
    if not db_obj or not hmac.compare_digest(db_obj.token_hash, token_hash):
        # Idempotent revoke
        return {"status": "ok"}

    db_obj.revoked = True
    db.commit()

    # Lazy cleanup con baja probabilidad
    if random.random() < _LAZY_CLEANUP_PROB:
        _lazy_cleanup(db)

    return {"status": "ok"}
