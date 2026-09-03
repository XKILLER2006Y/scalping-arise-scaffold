from fastapi import APIRouter
from pydantic import BaseModel
from app.signals.engine import decide

router = APIRouter(prefix="/signals", tags=["signals"])

class Req(BaseModel):
    evaluations: list[dict]
    features: dict

@router.get("/health")
def health():
    return {"status": "ok", "module": "signals", "phase": 6}

@router.post("/decide")
def run(req: Req):
    return decide(req.evaluations, req.features)
