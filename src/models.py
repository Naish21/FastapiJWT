from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Integer,
    Boolean,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    jti = Column(String(64), unique=True, nullable=False)
    subject = Column(String(128), nullable=False)
    token_hash = Column(String(128), nullable=False)
    issued_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("jti", name="uq_refresh_jti"),
        Index("ix_refresh_subject", "subject"),
        Index("ix_refresh_expires", "expires_at"),
    )
