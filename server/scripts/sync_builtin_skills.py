#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path


def _bootstrap_import_path() -> None:
    server_dir = Path(__file__).resolve().parents[1]
    os.chdir(server_dir)
    server_dir_str = str(server_dir)
    if server_dir_str not in sys.path:
        sys.path.insert(0, server_dir_str)


_bootstrap_import_path()

from app.builtin_skill_loader import ensure_builtin_skills_for_user  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402


def main() -> int:
    db = SessionLocal()
    try:
        users = db.query(User).all()
        created_total = 0
        for user in users:
            created = ensure_builtin_skills_for_user(db, user_id=user.id)
            created_total += len(created)

        if created_total:
            db.commit()
        else:
            db.rollback()

        print(f"users={len(users)} created_skills={created_total}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
