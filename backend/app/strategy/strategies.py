"""Phase 5: explicit strategy definitions. Evaluation only — no orders."""
STRATEGIES = {
    "TREND_CONT": {
        "description": "Trend continuation: trade with BOS-confirmed trend, EMA stack, RSI momentum, pullback entry.",
        "timeframes": {"bias": "15m", "structure": "5m", "entry": "1m"},
        "rules": [
            "trend is UPTREND or DOWNTREND (no RANGE)",
            "close above EMA20 above EMA50 for long / below for short",
            "RSI 50-70 long / 30-50 short",
            "volatility NORMAL or HIGH (never LOW/EXTREME)",
            "ADX>=20 trend strength; ATR-ratio 0.4-2.0 (no dead/spike market)",
            "BOS true",
            "Phase 6 entry additionally requires: killzone session (LONDON/NEW_YORK) + 1-3 bar pullback (ARMED→ENTRY)",
        ],
    },
    "RANGE_FADE": {
        "description": "Range fade at support/resistance with statistical extreme + exhaustion.",
        "timeframes": {"bias": "15m", "structure": "5m", "entry": "1m"},
        "rules": [
            "trend is RANGE",
            "price within 0.5*ATR of support (long) or resistance (short)",
            "RSI <30 long / >70 short OR outside Bollinger",
            "|Z-score|>=2.0 statistical extreme; ADX<=22 ranging",
            "volatility LOW or NORMAL (never HIGH/EXTREME)",
        ],
    },
}
