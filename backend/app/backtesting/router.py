from fastapi import APIRouter
from pydantic import BaseModel
from app.market_data.models import Candle
from app.backtesting.engine import run_backtest

router = APIRouter(prefix="/backtest", tags=["backtest"])

class Req(BaseModel):
    candles: list[Candle]
    equity: float = 10000.0
    risk_pct: float = 1.0

@router.get("/health")
def health():
    return {"status": "ok", "module": "backtesting", "phase": 9}

@router.post("/run")
def run(req: Req):
    return run_backtest(req.candles, req.equity, req.risk_pct)
