from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .api import admin as admin_router
from .api import agent as agent_router
from .api import auth as auth_router
from .api import models as models_router
from .api import threads as threads_router
from .api import workspace as workspace_router
from .auth import hash_password
from .config import load_config
from .db import SessionLocal
from .model_catalog import DEFAULT_MODEL_ID
from .models import AppSetting, User

app = FastAPI(title="Openwork Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5176",
        "http://127.0.0.1:5176",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(admin_router.router)
app.include_router(threads_router.router)
app.include_router(models_router.router)
app.include_router(workspace_router.router)
app.include_router(agent_router.router)


@app.on_event("startup")
def startup() -> None:
    cfg = load_config()

    # Ensure workspace root exists
    Path(cfg.workspace.root).mkdir(parents=True, exist_ok=True)

    # Ensure admin user exists
    db: Session = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == cfg.admin.email).first()
        if not admin:
            admin = User(
                username=cfg.admin.email.split("@")[0],
                email=cfg.admin.email,
                password_hash=hash_password(cfg.admin.password),
                is_admin=True,
            )
            db.add(admin)
            db.commit()
        default_model = db.get(AppSetting, "default_model")
        if not default_model:
            db.add(AppSetting(key="default_model", value=DEFAULT_MODEL_ID))
            db.commit()

    finally:
        db.close()

    # Serve static frontend if built
    dist = Path("web/dist")
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="static")
