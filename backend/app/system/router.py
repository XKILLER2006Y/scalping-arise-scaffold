from fastapi import APIRouter
from pydantic import BaseModel
from app.market_data.models import Candle
from app.system.engine import full_trace, system_health, reliability, _forward_log

router = APIRouter(prefix="/system", tags=["system"])

class Req(BaseModel):
    symbol: str = "XAU/USD"
    candles_1m: list[Candle]
    candles_5m: list[Candle] = []
    candles_15m: list[Candle] = []
    equity: float = 10000.0
    risk_pct: float = 1.0
    spread: float = 0.3

@router.get("/health")
def health():
    return system_health()

@router.post("/trace")
def trace(req: Req):
    c5 = req.candles_5m or req.candles_1m
    c15 = req.candles_15m or req.candles_1m
    return full_trace(req.candles_1m, c5, c15, req.symbol, req.equity, req.risk_pct, req.spread)

@router.get("/reliability")
def rel():
    return reliability()

@router.get("/forward")
def fwd(limit: int = 50):
    return {"entries": _forward_log[-limit:][::-1], "total": len(_forward_log)}

@router.get("/trace-quick")
def trace_quick(symbol: str = "XAU/USD", limit: int = 250, equity: float = 10000.0,
                risk_pct: float = 1.0, spread: float = 0.3):
    """Full pipeline with server-side data fetch (no candle upload needed)."""
    from app.market_data.service import get_candles
    c1, _ = get_candles(symbol, "1m", limit)
    c5, _ = get_candles(symbol, "5m", limit)
    c15, _ = get_candles(symbol, "15m", limit)
    return full_trace(c1, c5, c15, symbol, equity, risk_pct, spread)
