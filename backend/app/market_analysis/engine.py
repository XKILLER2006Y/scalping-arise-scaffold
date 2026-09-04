"""Phase 3: structure only. No signals. + sweep/FVG detectors (descriptive)."""
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
    sweeps: list[dict] = []  # liquidity sweeps (wick beyond swing, close back inside)
    fvgs: list[dict] = []  # fair value gaps (3-candle imbalance), unfilled
    source_type: SourceType
    candle_count: int

    def get(self, key: str, default=None):
        return getattr(self, key, default)

    def __getitem__(self, key: str):
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def __contains__(self, key: str):
        return hasattr(self, key)

    def keys(self):
        return self.__dict__.keys()

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

def detect_sweeps(candles: list[Candle], highs: list[int], lows: list[int], lookback: int = 30) -> list[dict]:
    # Sell-side sweep: low wicks below last swing low but closes back above. Mirror for buy-side.
    out = []
    if not candles:
        return out
    recent_highs = highs[-3:]
    recent_lows = lows[-3:]
    for i in range(max(0, len(candles) - lookback), len(candles)):
        c = candles[i]
        for s in recent_lows:
            if s < i and c.low < candles[s].low and c.close > candles[s].low:
                out.append({"type": "SSL_SWEEP", "i": i, "level": round(candles[s].low, 2)})
                break
        for s in recent_highs:
            if s < i and c.high > candles[s].high and c.close < candles[s].high:
                out.append({"type": "BSL_SWEEP", "i": i, "level": round(candles[s].high, 2)})
                break
    return out[-5:]

def detect_fvg(candles: list[Candle], lookback: int = 30) -> list[dict]:
    # Bullish FVG: low[i] > high[i-2] (gap between candle i-2 high and candle i low)
    out = []
    start = max(2, len(candles) - lookback)
    for i in range(start, len(candles)):
        a, b, c = candles[i-2], candles[i-1], candles[i]
        if c.low > a.high:
            out.append({"dir": "BULL", "i": i, "top": round(c.low, 2), "bottom": round(a.high, 2)})
        elif c.high < a.low:
            out.append({"dir": "BEAR", "i": i, "top": round(a.low, 2), "bottom": round(c.high, 2)})
    return out[-5:]

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
    bos = bool(highs and candles[-1].close > candles[highs[-1]].high) or bool(lows and candles[-1].close < candles[lows[-1]].low)
    choch = len(highs) >= 2 and len(lows) >= 2 and trend == "RANGE" and bos
    closes = [c.close for c in candles[-50:]]
    rng = max(closes) - min(closes) if closes else 0
    avg = sum(closes) / len(closes) if closes else 1.0
    if avg <= 0: avg = 1.0
    regime = "VOLATILE" if rng / avg > 0.004 else ("TRENDING" if trend != "RANGE" else "RANGING")
    sup = sorted(set(round(c.low, 2) for c in candles[-30:]))[:3] if candles else []
    res = sorted(set(round(c.high, 2) for c in candles[-30:]))[-3:] if candles else []
    st = candles[0].source_type if candles else SourceType.SPOT
    import datetime
    hr = datetime.datetime.now(datetime.timezone.utc).hour
    sess = "LONDON" if 7 <= hr < 12 else ("NEW_YORK" if 12 <= hr < 17 else ("ASIA" if hr >= 22 or hr < 7 else "OFF"))
    return AnalysisResult(symbol=symbol, trend=trend, regime=regime, session=sess,
                          swings_high=highs[-5:], swings_low=lows[-5:], bos=bos, choch=choch,
                          support=sup, resistance=res,
                          sweeps=detect_sweeps(candles, highs, lows) if candles else [],
                          fvgs=detect_fvg(candles) if candles else [],
                          source_type=st, candle_count=len(candles))


analyze_market = analyze

