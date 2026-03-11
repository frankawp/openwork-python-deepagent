from __future__ import annotations

import base64
from cryptography.fernet import Fernet

from .config import load_config


def _fernet() -> Fernet:
    cfg = load_config()
    key = cfg.auth.jwt_secret.encode("utf-8")
    # Derive 32-byte key from jwt_secret (not ideal, but avoids extra secret)
    key_bytes = key[:32].ljust(32, b"0")
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt(text: str) -> str:
    return _fernet().encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
