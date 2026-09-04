"""Phase 5 engine: does market satisfy strategy? Returns qualified + breakdown."""

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

def eval_trend_cont(analysis: dict, feats: dict, mtf: dict | None = None) -> dict:
    met, missing = [], []
    bias = (mtf or {}).get("bias") or {}
    bias_trend = bias.get("trend")
    trend = bias_trend if bias_trend in ("UPTREND", "DOWNTREND") else analysis.get("trend")
    if bias_trend in ("UPTREND", "DOWNTREND"):
        met.append(f"HTF bias={bias_trend}")
    entry_trend = analysis.get("trend")
    if trend in ("UPTREND", "DOWNTREND"):
        met.append(f"trend={trend}")
        if entry_trend not in (trend, "RANGE"):
            missing.append(f"entry timeframe disagrees (bias {trend} vs entry {entry_trend})")
    else:
        missing.append(f"trend must be UPTREND/DOWNTREND, got {trend}")
    rsi = feats.get("rsi14")
    direction = "LONG" if trend == "UPTREND" else ("SHORT" if trend == "DOWNTREND" else None)
    if direction == "LONG":
        (met if _ema_stack_bull(feats) else missing).append("EMA20>EMA50" if _ema_stack_bull(feats) else "EMA stack not bullish")
        if rsi is not None and 50 <= rsi <= 80:
            met.append(f"RSI {rsi:.1f} in 50-80 (trend zone)")
        else:
            missing.append(f"RSI {rsi} not in 50-80")
    elif direction == "SHORT":
        (met if _ema_stack_bear(feats) else missing).append("EMA20<EMA50" if _ema_stack_bear(feats) else "EMA stack not bearish")
        if rsi is not None and 20 <= rsi <= 50:
            met.append(f"RSI {rsi:.1f} in 20-50 (trend zone)")
        else:
            missing.append(f"RSI {rsi} not in 20-50")
    else:
        missing.append("no direction (trend RANGE)")
    vol = feats.get("_volatility") or feats.get("volatility") or ""
    if vol in ("NORMAL_VOLATILITY", "HIGH_VOLATILITY"):
        met.append(f"volatility={vol}")
    else:
        missing.append(f"volatility {vol} not NORMAL/HIGH")
    adx = feats.get("adx14")
    if adx is not None and adx >= 20:
        met.append(f"ADX {adx:.1f}>=20 trend strength")
    else:
        missing.append(f"ADX {adx} < 20 (no trend strength)")
    ratio = feats.get("atr_ratio")
    if ratio is not None and 0.4 <= ratio <= 2.0:
        met.append(f"ATR-ratio {ratio:.2f} in 0.4-2.0")
    else:
        missing.append(f"ATR-ratio {ratio} outside 0.4-2.0 (dead/spike)")
    if analysis.get("bos"):
        met.append("BOS=true")
    else:
        missing.append("BOS=false")
    score = round(100 * len(met) / max(1, len(met) + len(missing)))
    return {"strategy": "TREND_CONT", "direction": direction, "qualified": not missing,
            "quality": score, "met": met, "missing": missing}

def eval_range_fade(analysis: dict, feats: dict, entry_price: float | None = None,
                       mtf: dict | None = None) -> dict:
    met, missing = [], []
    trend = analysis.get("trend")
    bias = (mtf or {}).get("bias") or {}
    if trend == "RANGE":
        met.append("trend=RANGE")
        if bias.get("trend") in ("UPTREND", "DOWNTREND"):
            missing.append(f"HTF bias {bias.get('trend')} trends — no fading against it")
    else:
        missing.append(f"trend must be RANGE, got {trend}")
    atr = feats.get("atr14") or 0
    px = entry_price if entry_price is not None else feats.get("_close")
    sup = (analysis.get("support") or [None])[0]
    res = (analysis.get("resistance") or [None])[-1] if analysis.get("resistance") else None
    direction = None
    if px is not None and sup is not None and atr and abs(px - sup) <= 1.0 * atr:
        direction = "LONG"; met.append(f"near support {sup}")
    elif px is not None and res is not None and atr and abs(px - res) <= 1.0 * atr:
        direction = "SHORT"; met.append(f"near resistance {res}")
    else:
        missing.append("price not within 1.0*ATR of S/R")
    rsi = feats.get("rsi14")
    bb_up, bb_lo = feats.get("bb_up"), feats.get("bb_lo")
    exhausted = (rsi is not None and (rsi < 30 or rsi > 70)) or \
                (px is not None and bb_up is not None and bb_lo is not None and (px >= bb_up or px <= bb_lo))
    if exhausted:
        met.append(f"exhaustion RSI={rsi}")
    else:
        missing.append(f"no exhaustion RSI={rsi}")
    vol = feats.get("_volatility") or feats.get("volatility") or ""
    if vol in ("LOW_VOLATILITY", "NORMAL_VOLATILITY"):
        met.append(f"volatility={vol}")
    else:
        missing.append(f"volatility {vol} not LOW/NORMAL")
    z = feats.get("z20")
    if z is not None and abs(z) >= 2.0:
        met.append(f"|Z| {abs(z):.2f}>=2.0 statistical extreme")
    else:
        missing.append(f"|Z| {z} < 2.0 (no extreme)")
    adx = feats.get("adx14")
    if adx is not None and adx <= 22:
        met.append(f"ADX {adx:.1f}<=22 ranging")
    else:
        missing.append(f"ADX {adx} > 22 (trending, skip fade)")
    score = round(100 * len(met) / max(1, len(met) + len(missing)))
    return {"strategy": "RANGE_FADE", "direction": direction, "qualified": (not missing and direction is not None),
            "quality": score, "met": met, "missing": missing}



def _pullback_ok(direction: str | None, closes: list[float] | None) -> bool:
    # Local copy of the Phase 6 pullback rule (strategy must not import Phase 6):
    # 1-3 counter-trend closes in the last 5.
    if not direction or not closes or len(closes) < 6:
        return False
    last5 = [closes[i] - closes[i - 1] for i in range(len(closes) - 5, len(closes))]
    counter = sum(1 for d in last5 if (d < 0 if direction == "LONG" else d > 0))
    return 1 <= counter <= 3


def eval_pullback_cont(analysis: dict, feats: dict, closes: list[float] | None = None,
                       mtf: dict | None = None) -> dict:
    """Standalone pullback-continuation strategy (ported concept from friend's
    pullback_continuation: underlying trend + pullback + S/R + momentum recovery)."""
    met, missing = [], []
    bias = (mtf or {}).get("bias") or {}
    trend = bias.get("trend") if bias.get("trend") in ("UPTREND", "DOWNTREND") else analysis.get("trend")
    direction = "LONG" if trend == "UPTREND" else ("SHORT" if trend == "DOWNTREND" else None)
    if direction:
        src = "HTF bias" if bias.get("trend") == trend else "entry timeframe"
        met.append(f"underlying trend={trend} ({src})")
    else:
        missing.append(f"no underlying trend (got {trend})")
        return {"strategy": "PULLBACK_CONT", "direction": direction, "qualified": False,
                "quality": 0, "met": met, "missing": missing}
    if _pullback_ok(direction, closes or []):
        met.append("pullback detected (1-3 counter-trend closes in last 5)")
    else:
        missing.append("no pullback signature (need 1-3 counter-trend closes in last 5)")
    atr = feats.get("atr14") or 0
    px = feats.get("_close")
    ema20 = feats.get("ema20")
    near_ema = px is not None and ema20 is not None and atr and abs(px - ema20) <= 0.5 * atr
    sup = (analysis.get("support") or [None])[0]
    res = (analysis.get("resistance") or [None])[-1] if analysis.get("resistance") else None
    near_sr = px is not None and atr and (
        (sup is not None and abs(px - sup) <= 1.0 * atr) or
        (res is not None and abs(px - res) <= 1.0 * atr))
    if near_ema or near_sr:
        met.append("price near EMA20 or S/R zone")
    else:
        missing.append("price not near EMA20 nor S/R zone")
    rsi = feats.get("rsi14")
    if rsi is not None and 35 <= rsi <= 65:
        met.append(f"RSI {rsi:.1f} recovering toward neutral")
    else:
        missing.append(f"RSI {rsi} not in 35-65 recovery band")
    vol = feats.get("_volatility") or feats.get("volatility") or ""
    if vol in ("NORMAL_VOLATILITY", "HIGH_VOLATILITY"):
        met.append(f"volatility={vol}")
    else:
        missing.append(f"volatility {vol} not NORMAL/HIGH")
    adx = feats.get("adx14")
    if adx is not None and adx >= 20:
        met.append(f"ADX {adx:.1f}>=20")
    else:
        missing.append(f"ADX {adx} < 20")
    ratio = feats.get("atr_ratio")
    if ratio is not None and 0.4 <= ratio <= 2.0:
        met.append(f"ATR-ratio {ratio:.2f} in range")
    else:
        missing.append(f"ATR-ratio {ratio} outside 0.4-2.0")
    score = round(100 * len(met) / max(1, len(met) + len(missing)))
    return {"strategy": "PULLBACK_CONT", "direction": direction, "qualified": not missing,
            "quality": score, "met": met, "missing": missing}

def evaluate_all(analysis: dict, features: dict, close: float | None = None,
                 closes: list[float] | None = None, candle_count: int = 0,
                 source_type: str = "SPOT", mtf: dict | None = None) -> list[dict]:
    """Evaluate all strategies with eligibility pre-check and invalidation veto.

    mtf optionally carries higher-timeframe analyses: {"bias": {...}, "structure": {...}}.
    Trend direction comes from the bias TF when available (a 1m pullback must not be
    allowed to erase the trend it pulls back from); without mtf, single-TF behavior.
    """
    from app.strategy.eligibility import check_eligibility
    from app.strategy.invalidation import evaluate_invalidation
    feats = dict(features)
    feats["_close"] = close
    out = []
    for sid, ev in (("TREND_CONT", eval_trend_cont(analysis, feats, mtf)),
                    ("PULLBACK_CONT", eval_pullback_cont(analysis, feats, closes, mtf)),
                    ("RANGE_FADE", eval_range_fade(analysis, feats, entry_price=close, mtf=mtf))):
        elig = check_eligibility(sid, analysis, feats, candle_count or len(closes or []), source_type)
        ev["eligibility"] = elig
        if not elig["eligible"]:
            ev["qualified"] = False
            ev["quality"] = 0
            ev["missing"] = ev.get("missing", []) + [f"ineligible: {elig['blocked_by']}"]
            ev["invalidation"] = []
            out.append(ev)
            continue
        inv = evaluate_invalidation(sid, analysis, ev.get("direction"), feats, closes or [])
        ev["invalidation"] = inv
        vetoes = [r for r in inv if r["triggered"]]
        if vetoes and ev.get("qualified"):
            ev["qualified"] = False
            ev["missing"] = ev.get("missing", []) + [f"invalidated: {r['rule_id']} ({r['reason']})" for r in vetoes]
        out.append(ev)
    return out
