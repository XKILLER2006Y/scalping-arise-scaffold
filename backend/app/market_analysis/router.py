from fastapi import APIRouter
from pydantic import BaseModel
from app.market_data.models import Candle
from app.market_analysis.engine import analyze

router = APIRouter(prefix="/market-analysis", tags=["market-analysis"])

class Req(BaseModel):
    symbol: str = "XAU/USD"
    candles: list[Candle]

@router.get("/health")
def health():
    return {"status": "ok", "module": "market_analysis"}

@router.get("/capabilities")
def caps():
    return {"functions": ["swings", "HH/HL/LH/LL", "trend", "BOS", "CHOCH", "support/resistance", "session", "regime"],
            "note": "analysis only, no signals"}

@router.post("")
def run(req: Req):
    return analyze(req.candles, req.symbol).model_dump()
