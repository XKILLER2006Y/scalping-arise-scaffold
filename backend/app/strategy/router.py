from fastapi import APIRouter, Query
from pydantic import BaseModel
from app.strategy.strategies import STRATEGIES
from app.strategy.engine import evaluate_all

router = APIRouter(prefix="/strategy", tags=["strategy"])

class Req(BaseModel):
    analysis: dict
    features: dict
    close: float | None = None
    closes: list[float] | None = None
    candle_count: int = 0
    source_type: str = "SPOT"
    mtf: dict | None = None  # {"bias": {...}, "structure": {...}} HTF analyses

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
    return {"evaluations": evaluate_all(req.analysis, feats, req.close, req.closes,
                                       req.candle_count, req.source_type, req.mtf)}


@router.get("/evaluate-quick")
def evaluate_quick(symbol: str = "XAU/USD", timeframe: str = Query("1m"), limit: int = Query(250, le=500)):
    """Fetch candles internally then evaluate (friend-style GET UX; same engine as POST)."""
    from app.market_data.service import get_candles
    from app.market_analysis.engine import analyze
    from app.market_data.resample import resample, closed_asof
    from app.technical_features.engine import compute_single_timeframe
    candles, mmeta = get_candles(symbol, timeframe, limit)
    a = analyze(candles, symbol)
    htf5 = resample(candles, "5m")
    htf15 = resample(candles, "15m")
    ts = candles[-1].timestamp if candles else 0
    c5, c15 = closed_asof(htf5, ts), closed_asof(htf15, ts)
    a5 = analyze(c5, symbol) if len(c5) >= 20 else None
    a15 = analyze(c15, symbol) if len(c15) >= 20 else None
    htf = {"bias": (a15 or a5 or a).model_dump(), "structure": (a5 or a).model_dump()}
    f = compute_single_timeframe(candles, timeframe, symbol)
    feats = dict(f["features"])
    feats["volatility"] = f["volatility"]
    feats["_volatility"] = f["volatility"]
    evs = evaluate_all(a.model_dump(), feats, candles[-1].close if candles else None,
                       closes=[c.close for c in candles], candle_count=len(candles),
                       source_type=str(candles[0].source_type) if candles else "SPOT",
                       mtf=htf)
    return {"symbol": symbol, "timeframe": timeframe, "market_meta": mmeta,
            "analysis": a.model_dump(), "features_status": f["status"],
            "evaluations": evs}
