from fastapi import APIRouter
from pydantic import BaseModel
from app.market_data.models import Candle
from app.validation import engine as v

router = APIRouter(prefix="/validation", tags=["validation"])

class Req(BaseModel):
    candles: list[Candle]
    equity: float = 10000.0
    risk_pct: float = 1.0
    warmup: int = 200
    folds: int = 3
    grid: dict | None = None  # e.g. {"sl_mult":[1.5],"tp_mult":[2.0],"min_conf":[60]} for quick checks

@router.get("/health")
def health():
    return {"status": "ok", "module": "validation", "phase": "wave-1",
            "methods": ["walk-forward", "monte-carlo", "sensitivity", "benchmark-gate"]}

@router.post("/walk-forward")
def wf(req: Req):
    return v.walk_forward(req.candles, req.folds, req.equity, req.risk_pct, req.warmup, req.grid)

@router.post("/monte-carlo")
def mc(req: Req):
    base = v.run_backtest(req.candles, req.equity, req.risk_pct, req.warmup, return_all_trades=True)
    return v.monte_carlo([t["pnl"] for t in base.get("trades_full", [])])

@router.post("/sensitivity")
def sens(req: Req):
    return v.sensitivity(req.candles, req.equity, req.risk_pct, req.warmup, req.grid)

@router.post("/full-audit")
def audit(req: Req):
    return v.full_audit(req.candles, req.equity, req.risk_pct, req.warmup, req.folds, req.grid)
