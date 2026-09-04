"""Eligibility gate (Phase 5 pre-check).

Adapted with permission from Hash-sudo-cell/scalping-arise
(backend/app/modules/strategies/eligibility.py): cheap checks run BEFORE
detailed evaluation — data present, candles sufficient, features ready,
source policy, regime compatible. A blocked strategy skips evaluation.
"""

STRATEGY_REGIMES = {
    "TREND_CONT": ("UPTREND", "DOWNTREND"),
    "PULLBACK_CONT": ("UPTREND", "DOWNTREND"),
    "RANGE_FADE": ("RANGE",),
}

MIN_CANDLES = 50
FULL_CANDLES = 200  # EMA200 warm-up


def check_eligibility(strategy_id: str, analysis: dict, features: dict,
                      candle_count: int, source_type: str = "SPOT") -> dict:
    checks: list[dict] = []
    blocked_by: str | None = None

    def add(name: str, passed: bool, reason: str):
        nonlocal blocked_by
        checks.append({"check": name, "passed": passed, "reason": reason})
        if not passed and blocked_by is None:
            blocked_by = name

    add("analysis_available", bool(analysis and analysis.get("trend")),
        "Trend present" if analysis and analysis.get("trend") else "No analysis/trend")
    add("candles_sufficient", candle_count >= MIN_CANDLES,
        f"{candle_count} candles (min {MIN_CANDLES})")
    feats_ready = all(features.get(k) is not None for k in ("ema20", "rsi14", "atr14"))
    add("features_ready", feats_ready,
        "ema20/rsi14/atr14 present" if feats_ready else "Missing core features (still warming up?)")
    # All three strategies allow FUTURES_PROXY (friend's FUTURES_PROXY_ALLOWED policy).
    add("source_compatible", source_type in ("SPOT", "FUTURES_PROXY"),
        f"source_type={source_type}")
    ok_regimes = STRATEGY_REGIMES.get(strategy_id, ())
    add("regime_compatible", (analysis.get("trend") if analysis else None) in ok_regimes,
        f"trend={analysis.get('trend') if analysis else None}, needs one of {ok_regimes}")
    if candle_count < FULL_CANDLES:
        checks.append({"check": "full_warmup", "passed": True,
                       "reason": f"Partial warm-up ({candle_count}/{FULL_CANDLES}): EMA200 unavailable, noted not blocking"})

    return {"strategy": strategy_id, "eligible": blocked_by is None,
            "blocked_by": blocked_by, "checks": checks}
