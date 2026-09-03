"""Phase 4 CORE engine. Descriptive only. Extension (MTF/vol/status) is PROPOSAL ONLY, not coded."""
from app.market_data.models import Candle
from app.technical_features.indicators import ema, rsi, macd, atr, bollinger

def compute_features(candles: list[Candle], symbol: str = "XAU/USD") -> dict:
    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    vols = [c.volume for c in candles if c.volume is not None]
    n = len(closes)
    e20, e50, e200 = ema(closes, 20), ema(closes, 50), ema(closes, 200)
    r = rsi(closes, 14)
    ml, sl, hl = macd(closes)
    a = atr(highs, lows, closes, 14)
    bm, bu, bl = bollinger(closes, 20, 2.0)
    last = n - 1
    def ready(v):
        return v is not None
    # volume optional
    vsma = sum(vols[-20:]) / min(20, len(vols)) if vols else None
    rel_vol = (vols[-1] / vsma) if vols and vsma else None
    price_change = closes[-1] - closes[-2] if n >= 2 else 0
    window = closes[-20:]
    rng = max(window) - min(window) if window else 0
    pos = (closes[-1] - min(window)) / rng if rng else 0.5
    st = candles[0].source_type if candles else "SPOT"
    return {
        "symbol": symbol, "candle_count": n, "source_type": st,
        "ema20": e20[last], "ema50": e50[last], "ema200": e200[last],
        "rsi14": r[last], "macd_line": ml[last], "macd_signal": sl[last], "macd_hist": hl[last],
        "atr14": a[last], "bb_mid": bm[last], "bb_up": bu[last], "bb_lo": bl[last],
        "vol_sma20": vsma, "rel_volume": rel_vol,
        "price_change": price_change, "price_range": rng, "position_in_range": pos,
        "availability": {
            "ema20": ready(e20[last]), "ema50": ready(e50[last]), "ema200": ready(e200[last]),
            "rsi14": ready(r[last]), "macd": ready(ml[last]), "atr14": ready(a[last]),
        },
        "note": "CORE only. No MTF, no volatility class, no READY/WARMING_UP status, no signals.",
    }
