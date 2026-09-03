from fastapi import APIRouter
from pydantic import BaseModel
from app.trade_planning.engine import plan

router = APIRouter(prefix="/trade-plan", tags=["trade-plan"])

class Req(BaseModel):
    signal: dict
    entry: float
    atr: float | None = None
    equity: float = 10000.0
    risk_pct: float = 1.0
    spread: float = 0.3

@router.get("/health")
def health():
    return {"status": "ok", "module": "trade_planning", "phase": 7}

@router.post("")
def run(req: Req):
    return plan(req.signal, req.entry, req.atr, req.equity, req.risk_pct, req.spread)
