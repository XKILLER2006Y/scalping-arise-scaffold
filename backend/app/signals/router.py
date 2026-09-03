from fastapi import APIRouter
from pydantic import BaseModel
from app.signals.engine import decide

router = APIRouter(prefix="/signals", tags=["signals"])

class Req(BaseModel):
    evaluations: list[dict]
    features: dict
    context: dict | None = None  # {session, closes, analysis}

@router.get("/health")
def health():
    return {"status": "ok", "module": "signals", "phase": 6,
            "gates": ["killzone LONDON/NEW_YORK", "ARMED pullback 1-3/5", "sweep confluence", "conflict resolver"]}

@router.post("/decide")
def run(req: Req):
    return decide(req.evaluations, req.features, req.context)
