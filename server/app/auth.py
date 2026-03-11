from __future__ import annotations

import datetime as dt
from typing import Optional

from jose import jwt
from passlib.hash import pbkdf2_sha256

from .config import load_config
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pbkdf2_sha256.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pbkdf2_sha256.verify(password, hashed)


def create_access_token(subject: str) -> str:
    cfg = load_config()
    now = dt.datetime.utcnow()
    exp = now + dt.timedelta(minutes=cfg.auth.access_ttl_min)
    payload = {"sub": subject, "type": "access", "iat": now, "exp": exp}
    return jwt.encode(payload, cfg.auth.jwt_secret, algorithm=ALGORITHM)


def create_refresh_token(subject: str) -> str:
    cfg = load_config()
    now = dt.datetime.utcnow()
    exp = now + dt.timedelta(days=cfg.auth.refresh_ttl_days)
    payload = {"sub": subject, "type": "refresh", "iat": now, "exp": exp}
    return jwt.encode(payload, cfg.auth.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    cfg = load_config()
    try:
        return jwt.decode(token, cfg.auth.jwt_secret, algorithms=[ALGORITHM])
    except Exception:
        return None
