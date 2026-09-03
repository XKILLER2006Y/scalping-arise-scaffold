from fastapi import APIRouter
from pydantic import BaseModel
from app.market_data.models import Candle
from app.technical_features.engine import compute_features

router = APIRouter(prefix="/technical-features", tags=["technical-features"])

class Req(BaseModel):
    symbol: str = "XAU/USD"
    candles: list[Candle]

@router.get("/health")
def health():
    return {"status": "ok", "module": "technical_features", "phase": "4-core"}

@router.get("/capabilities")
def caps():
    return {"indicators": ["EMA20/50/200", "RSI14", "MACD12/26/9", "ATR14", "BB20/2", "VolSMA20", "price features"],
            "extension": "PLANNED, NOT IMPLEMENTED: MTF 1m/5m/15m, volatility class, READY/WARMING_UP/UNAVAILABLE"}

@router.post("")
def run(req: Req):
    return compute_features(req.candles, req.symbol)
