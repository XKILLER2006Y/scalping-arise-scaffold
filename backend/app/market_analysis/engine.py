"""Phase 3: structure only. No signals."""
from pydantic import BaseModel
from app.market_data.models import Candle, SourceType

class AnalysisResult(BaseModel):
    symbol: str
    trend: str  # UPTREND | DOWNTREND | RANGE
    regime: str  # TRENDING | RANGING | VOLATILE | QUIET
    session: str
    swings_high: list[int]
    swings_low: list[int]
    bos: bool
    choch: bool
    support: list[float]
    resistance: list[float]
    source_type: SourceType
    candle_count: int

def detect_swings(candles: list[Candle], left: int = 2, right: int = 2):
    highs, lows = [], []
    hs = [c.high for c in candles]
    ls = [c.low for c in candles]
    for i in range(left, len(candles) - right):
        if hs[i] == max(hs[i-left:i+right+1]):
            highs.append(i)
        if ls[i] == min(ls[i-left:i+right+1]):
            lows.append(i)
    return highs, lows

def classify_trend(candles: list[Candle]) -> str:
    if len(candles) < 20:
        return "RANGE"
    sma20 = sum(c.close for c in candles[-20:]) / 20
    sma50 = sum(c.close for c in candles[-50:]) / 50 if len(candles) >= 50 else sma20
    if candles[-1].close > sma20 > sma50:
        return "UPTREND"
    if candles[-1].close < sma20 < sma50:
        return "DOWNTREND"
    return "RANGE"

def analyze(candles: list[Candle], symbol: str = "XAU/USD") -> AnalysisResult:
    highs, lows = detect_swings(candles)
    trend = classify_trend(candles)
    # BOS/CHOCH simplified: break of last swing
    bos = bool(highs and candles[-1].close > candles[highs[-1]].high) or bool(lows and candles[-1].close < candles[lows[-1]].low)
    choch = len(highs) >= 2 and len(lows) >= 2 and trend == "RANGE" and bos
    closes = [c.close for c in candles[-50:]]
    rng = max(closes) - min(closes) if closes else 0
    avg = sum(closes) / len(closes) if closes else 1
    regime = "VOLATILE" if rng / avg > 0.004 else ("TRENDING" if trend != "RANGE" else "RANGING")
    sup = sorted(set(round(c.low, 2) for c in candles[-30:]))[:3] if candles else []
    res = sorted(set(round(c.high, 2) for c in candles[-30:]))[-3:] if candles else []
    st = candles[0].source_type if candles else SourceType.SPOT
    import datetime
    hr = datetime.datetime.utcnow().hour
    sess = "LONDON" if 7 <= hr < 12 else ("NEW_YORK" if 12 <= hr < 17 else ("ASIA" if hr >= 22 or hr < 7 else "OFF"))
    return AnalysisResult(symbol=symbol, trend=trend, regime=regime, session=sess,
                          swings_high=highs[-5:], swings_low=lows[-5:], bos=bos, choch=choch,
                          support=sup, resistance=res, source_type=st, candle_count=len(candles))
