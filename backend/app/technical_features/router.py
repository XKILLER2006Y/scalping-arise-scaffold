from fastapi import APIRouter, Query
from pydantic import BaseModel
from app.market_data.models import Candle
from app.technical_features.engine import compute_single_timeframe, compute_mtf, SUPPORTED_TFS

router = APIRouter(prefix="/technical-features", tags=["technical-features"])

class Req(BaseModel):
    symbol: str = "XAU/USD"
    candles: list[Candle]

class MtfReq(BaseModel):
    symbol: str = "XAU/USD"
    candles_by_timeframe: dict[str, list[Candle]]

@router.get("/health")
def health():
    return {"status": "ok", "module": "technical_features", "phase": "4-extension"}

@router.get("/capabilities")
def caps():
    return {"indicators": ["EMA20/50/200", "RSI14", "MACD12/26/9", "ATR14", "ATR-ratio", "Z20", "ADX14", "VWAP", "BB20/2", "VolSMA20", "price features"],
            "extension": "IMPLEMENTED in scaffold: MTF 1m/5m/15m, volatility class, READY/WARMING_UP/UNAVAILABLE + reason",
            "timeframes": SUPPORTED_TFS}

@router.post("")
def run(req: Req, timeframe: str = Query("1m")):
    tf = timeframe if timeframe in SUPPORTED_TFS else "1m"
    return compute_single_timeframe(req.candles, tf, req.symbol)

@router.post("/mtf")
def run_mtf(req: MtfReq):
    # Independent per-TF computation only. No decisions.
    filtered = {tf: req.candles_by_timeframe.get(tf, []) for tf in SUPPORTED_TFS}
    return compute_mtf(filtered, req.symbol)
