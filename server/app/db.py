from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import load_config


class Base(DeclarativeBase):
    pass


_ENGINE: Engine | None = None
_SESSION_FACTORY: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _ENGINE
    if _ENGINE is None:
        cfg = load_config()
        _ENGINE = create_engine(cfg.database.url, pool_pre_ping=True, future=True)
    return _ENGINE


def SessionLocal() -> Session:
    global _SESSION_FACTORY
    if _SESSION_FACTORY is None:
        _SESSION_FACTORY = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
        )
    return _SESSION_FACTORY()
