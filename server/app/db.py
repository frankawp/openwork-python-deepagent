from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import load_config


class Base(DeclarativeBase):
    pass


def get_engine():
    cfg = load_config()
    return create_engine(cfg.database.url, pool_pre_ping=True, future=True)


engine = get_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
