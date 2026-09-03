"""Phase 5 engine: does market satisfy strategy? Returns qualified + breakdown."""
from app.strategy.strategies import STRATEGIES

def _ema_stack_bull(f) -> bool:
    try:
        return f["ema20"] > f["ema50"]
    except Exception:
        return False

def _ema_stack_bear(f) -> bool:
    try:
        return f["ema20"] < f["ema50"]
    except Exception:
        return False

def eval_trend_cont(analysis: dict, feats: dict) -> dict:
    met, missing = [], []
    trend = analysis.get("trend")
    if trend in ("UPTREND", "DOWNTREND"):
        met.append(f"trend={trend}")
    else:
        missing.append(f"trend must be UPTREND/DOWNTREND, got {trend}")
    rsi = feats.get("rsi14")
    direction = "LONG" if trend == "UPTREND" else ("SHORT" if trend == "DOWNTREND" else None)
    if direction == "LONG":
        (met if _ema_stack_bull(feats) else missing).append("EMA20>EMA50" if _ema_stack_bull(feats) else "EMA stack not bullish")
        if rsi is not None and 50 <= rsi <= 70:
            met.append(f"RSI {rsi:.1f} in 50-70")
        else:
            missing.append(f"RSI {rsi} not in 50-70")
    elif direction == "SHORT":
        (met if _ema_stack_bear(feats) else missing).append("EMA20<EMA50" if _ema_stack_bear(feats) else "EMA stack not bearish")
        if rsi is not None and 30 <= rsi <= 50:
            met.append(f"RSI {rsi:.1f} in 30-50")
        else:
            missing.append(f"RSI {rsi} not in 30-50")
    else:
        missing.append("no direction (trend RANGE)")
    vol = feats.get("_volatility") or ""
    if vol in ("NORMAL_VOLATILITY", "HIGH_VOLATILITY"):
        met.append(f"volatility={vol}")
    else:
        missing.append(f"volatility {vol} not NORMAL/HIGH")
    if analysis.get("bos"):
        met.append("BOS=true")
    else:
        missing.append("BOS=false")
    score = round(100 * len(met) / max(1, len(met) + len(missing)))
    return {"strategy": "TREND_CONT", "direction": direction, "qualified": not missing,
            "quality": score, "met": met, "missing": missing}

def eval_range_fade(analysis: dict, feats: dict, entry_price: float | None = None) -> dict:
    met, missing = [], []
    trend = analysis.get("trend")
    if trend == "RANGE":
        met.append("trend=RANGE")
    else:
        missing.append(f"trend must be RANGE, got {trend}")
    atr = feats.get("atr14") or 0
    px = entry_price if entry_price is not None else feats.get("_close")
    sup = (analysis.get("support") or [None])[0]
    res = (analysis.get("resistance") or [None])[-1] if analysis.get("resistance") else None
    direction = None
    if px is not None and sup is not None and atr and abs(px - sup) <= 0.5 * atr:
        direction = "LONG"; met.append(f"near support {sup}")
    elif px is not None and res is not None and atr and abs(px - res) <= 0.5 * atr:
        direction = "SHORT"; met.append(f"near resistance {res}")
    else:
        missing.append("price not within 0.5*ATR of S/R")
    rsi = feats.get("rsi14")
    bb_up, bb_lo = feats.get("bb_up"), feats.get("bb_lo")
    exhausted = (rsi is not None and (rsi < 30 or rsi > 70)) or \
                (px is not None and bb_up is not None and bb_lo is not None and (px >= bb_up or px <= bb_lo))
    if exhausted:
        met.append(f"exhaustion RSI={rsi}")
    else:
        missing.append(f"no exhaustion RSI={rsi}")
    vol = feats.get("_volatility") or ""
    if vol in ("LOW_VOLATILITY", "NORMAL_VOLATILITY"):
        met.append(f"volatility={vol}")
    else:
        missing.append(f"volatility {vol} not LOW/NORMAL")
    score = round(100 * len(met) / max(1, len(met) + len(missing)))
    return {"strategy": "RANGE_FADE", "direction": direction, "qualified": (not missing and direction is not None),
            "quality": score, "met": met, "missing": missing}

def evaluate_all(analysis: dict, features: dict, close: float | None = None) -> list[dict]:
    feats = dict(features)
    feats["_close"] = close
    out = [eval_trend_cont(analysis, feats),
           eval_range_fade(analysis, feats, entry_price=close)]
    return out
