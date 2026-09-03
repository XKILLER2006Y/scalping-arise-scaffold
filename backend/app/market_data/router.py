from fastapi import APIRouter, Query
from app.market_data.service import get_candles

router = APIRouter(prefix="/market-data", tags=["market-data"])

@router.get("/health")
def health():
    return {"status": "ok", "module": "market_data"}

@router.get("/capabilities")
def capabilities():
    return {"primary": "twelve_data/SPOT XAU/USD", "fallback": "yfinance/GC=F FUTURES_PROXY",
            "timeframes": ["1m", "5m", "15m"], "features": ["normalization", "validation", "caching", "failover", "freshness", "gaps"]}

@router.get("/candles")
def candles(symbol: str = "XAU/USD", timeframe: str = Query("1m"), limit: int = Query(100, le=500)):
    data, meta = get_candles(symbol, timeframe, limit)
    return {"symbol": symbol, "timeframe": timeframe, "meta": meta, "candles": [c.model_dump() for c in data]}

@router.get("/latest")
def latest(symbol: str = "XAU/USD", timeframe: str = "1m"):
    data, meta = get_candles(symbol, timeframe, 1)
    return {"symbol": symbol, "meta": meta, "candle": data[-1].model_dump() if data else None}
