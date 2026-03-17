from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..crypto import decrypt, encrypt
from ..deep_agent_runtime import get_default_runtime_model_id
from ..deps import get_db, require_admin
from ..model_catalog import DEFAULT_MODEL_ID, MODELS, PROVIDERS
from ..models import AppSetting, GlobalApiKey
from ..schemas import ApiKeyIn, ModelConfigOut, ProviderOut

router = APIRouter(prefix="/models", tags=["models"])


def _get_default_model(db: Session) -> str:
    row = db.get(AppSetting, "default_model")
    return row.value if row else DEFAULT_MODEL_ID


@router.get("", response_model=list[ModelConfigOut])
def list_models(db: Session = Depends(get_db)):
    default_model = _get_default_model(db)
    keys = {row.provider for row in db.query(GlobalApiKey).all()}
    result = []
    for model in MODELS:
        result.append(
            ModelConfigOut(
                id=model.id,
                name=model.name,
                provider=model.provider,
                model=model.model,
                description=model.description,
                available=model.provider in keys,
            )
        )
    # Keep default model first in list to match UX expectation
    result.sort(key=lambda m: 0 if m.id == default_model else 1)
    return result


@router.get("/providers", response_model=list[ProviderOut])
def list_providers(db: Session = Depends(get_db)):
    keys = {row.provider for row in db.query(GlobalApiKey).all()}
    return [ProviderOut(id=p.id, name=p.name, hasApiKey=p.id in keys) for p in PROVIDERS]


@router.get("/default")
def get_default_model(db: Session = Depends(get_db)):
    return {
        "model_id": _get_default_model(db),
        "runtime_model_id": get_default_runtime_model_id(),
    }


@router.post("/default")
def set_default_model(
    payload: dict, db: Session = Depends(get_db), _admin=Depends(require_admin)
):
    model_id = payload.get("model_id") or payload.get("modelId")
    if not model_id:
        raise HTTPException(status_code=400, detail="model_id required")
    existing = db.get(AppSetting, "default_model")
    if existing:
        existing.value = model_id
    else:
        db.add(AppSetting(key="default_model", value=model_id))
    db.commit()
    return {"success": True}


@router.post("/api-key")
def set_api_key(
    payload: ApiKeyIn, db: Session = Depends(get_db), _admin=Depends(require_admin)
):
    encrypted = encrypt(payload.apiKey)
    existing = db.get(GlobalApiKey, payload.provider)
    if existing:
        existing.encrypted_key = encrypted
    else:
        db.add(GlobalApiKey(provider=payload.provider, encrypted_key=encrypted))
    db.commit()
    return {"success": True}


@router.delete("/api-key/{provider}")
def delete_api_key(provider: str, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    existing = db.get(GlobalApiKey, provider)
    if existing:
        db.delete(existing)
        db.commit()
    return {"success": True}


@router.get("/api-key/{provider}")
def get_api_key(provider: str, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    existing = db.get(GlobalApiKey, provider)
    if not existing:
        return {"apiKey": None}
    try:
        return {"apiKey": decrypt(existing.encrypted_key)}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to decrypt api key")
