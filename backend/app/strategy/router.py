from fastapi import APIRouter
from pydantic import BaseModel
from app.strategy.strategies import STRATEGIES
from app.strategy.engine import evaluate_all

router = APIRouter(prefix="/strategy", tags=["strategy"])

class Req(BaseModel):
    analysis: dict
    features: dict
    close: float | None = None

@router.get("/health")
def health():
    return {"status": "ok", "module": "strategy", "phase": 5}

@router.get("/capabilities")
def caps():
    return {"strategies": STRATEGIES, "note": "evaluation only, no signals"}

@router.post("/evaluate")
def evaluate(req: Req):
    feats = dict(req.features)
    # bridge Phase 4 extension volatility key
    if "_volatility" not in feats and "volatility" in req.features:
        feats["_volatility"] = req.features["volatility"]
    # allow flat Phase 4 single-TF shape
    return {"evaluations": evaluate_all(req.analysis, feats, req.close)}
