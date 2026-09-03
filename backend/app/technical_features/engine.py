"""Phase 4 + Extension: descriptive only. MTF independent, no cross-TF decisions, no signals."""
import time
from app.core.config import settings
from app.market_data.models import Candle
from app.technical_features.indicators import ema, rsi, macd, atr, bollinger, sma, zscore, adx, vwap

SUPPORTED_TFS = ["1m", "5m", "15m"]
FULL_READY_REQUIRED = 200  # EMA200 warm-up

def classify_volatility(atr_val: float | None, close: float | None) -> tuple[str | None, float | None]:
    if atr_val is None or close is None or close == 0:
        return None, None
    pct = atr_val / close
    if pct < settings.vol_low_max:
        return "LOW_VOLATILITY", pct
    if pct < settings.vol_normal_max:
        return "NORMAL_VOLATILITY", pct
    if pct < settings.vol_high_max:
        return "HIGH_VOLATILITY", pct
    return "EXTREME_VOLATILITY", pct

def get_status(n: int, ema200_ready: bool) -> tuple[str, str | None]:
    if n == 0:
        return "UNAVAILABLE", "no candles provided"
    if n < FULL_READY_REQUIRED or not ema200_ready:
        need = FULL_READY_REQUIRED
        return "WARMING_UP", f"need {need} candles for full features, have {n}"
    return "READY", None

def compute_single_timeframe(candles: list[Candle], timeframe: str, symbol: str = "XAU/USD") -> dict:
    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    vols = [c.volume for c in candles if c.volume is not None]
    n = len(closes)
    if n == 0:
        st = "SPOT"
        status, reason = get_status(0, False)
        return {"symbol": symbol, "timeframe": timeframe, "features": {}, "volatility": None,
                "atr_pct": None, "status": status, "reason": reason, "source_type": st,
                "provider_instrument": "XAU/USD", "candle_count": 0, "timestamp": int(time.time())}
    e20, e50, e200 = ema(closes, 20), ema(closes, 50), ema(closes, 200)
    r = rsi(closes, 14)
    ml, sl, hl = macd(closes)
    a = atr(highs, lows, closes, 14)
    bm, bu, bl = bollinger(closes, 20, 2.0)
    z = zscore(closes, 20)
    ax = adx(highs, lows, closes, 14)
    va = [c.volume for c in candles]
    vw = vwap(highs, lows, closes, va)
    # ATR ratio vs its own SMA20 (regime-normalized volatility, cf. Gold Snap Scalper)
    avals = [x for x in a if x is not None]
    asma = sma(avals, 20)
    atr_ratio = (avals[-1] / asma[-1]) if avals and asma and asma[-1] else None
    last = n - 1
    vsma = sum(vols[-20:]) / min(20, len(vols)) if vols else None
    rel_vol = (vols[-1] / vsma) if vols and vsma else None
    price_change = closes[-1] - closes[-2] if n >= 2 else 0.0
    window = closes[-20:]
    rng = max(window) - min(window) if window else 0.0
    pos = (closes[-1] - min(window)) / rng if rng else 0.5
    vol_class, atr_pct = classify_volatility(a[last], closes[last])
    e200_ready = e200[last] is not None
    status, reason = get_status(n, e200_ready)
    if vol_class is None and status == "READY":
        status, reason = "WARMING_UP", "ATR not ready for volatility classification"
    st = candles[0].source_type
    return {
        "symbol": symbol, "timeframe": timeframe,
        "features": {
            "ema20": e20[last], "ema50": e50[last], "ema200": e200[last],
            "rsi14": r[last], "macd_line": ml[last], "macd_signal": sl[last], "macd_hist": hl[last],
            "atr14": a[last], "atr_ratio": atr_ratio, "z20": z[last], "adx14": ax[last], "vwap": vw[last],
            "bb_mid": bm[last], "bb_up": bu[last], "bb_lo": bl[last],
            "vol_sma20": vsma, "rel_volume": rel_vol,
            "price_change": price_change, "price_range": rng, "position_in_range": pos,
        },
        "volatility": vol_class, "atr_pct": atr_pct,
        "status": status, "reason": reason,
        "source_type": st, "provider_instrument": candles[0].provider_instrument,
        "candle_count": n, "timestamp": int(time.time()),
    }

def compute_features(candles: list[Candle], symbol: str = "XAU/USD") -> dict:
    # Backward-compat single-TF (defaults 1m). Now includes extension fields.
    return compute_single_timeframe(candles, "1m", symbol)

def compute_mtf(candles_by_tf: dict[str, list[Candle]], symbol: str = "XAU/USD") -> dict:
    # Each TF computed independently from its own closed candles only.
    # No shifting/merging here — caller must pass only closed candles per TF.
    out: dict[str, dict] = {}
    for tf in SUPPORTED_TFS:
        out[tf] = compute_single_timeframe(candles_by_tf.get(tf, []), tf, symbol)
    return {"symbol": symbol, "timeframes": out,
            "note": "Descriptive only. No confirmation, no BUY/SELL/NO-TRADE."}
