"""Phase 5: explicit strategy definitions. Evaluation only — no orders."""
STRATEGIES = {
    "TREND_CONT": {
        "description": "Trend continuation: trade with BOS-confirmed trend, EMA stack, RSI momentum, pullback entry.",
        "timeframes": {"bias": "15m", "structure": "5m", "entry": "1m"},
        "rules": [
            "trend is UPTREND or DOWNTREND (no RANGE)",
            "close above EMA20 above EMA50 for long / below for short",
            "RSI 50-80 long / 20-50 short (trend zone, extremes excluded)",
            "volatility NORMAL or HIGH (never LOW/EXTREME)",
            "ADX>=20 trend strength; ATR-ratio 0.4-2.0 (no dead/spike market)",
            "BOS true",
            "Phase 6 entry additionally requires: killzone session (LONDON/NEW_YORK) + 1-3 bar pullback (ARMED→ENTRY)",
        ],
    },
    "PULLBACK_CONT": {
        "description": "Pullback continuation (ported w/ permission from Hash-sudo-cell/scalping-arise): established trend + temporary counter-trend pullback + recovery near EMA/S-R. Deep pullbacks (>61.8%) excluded.",
        "timeframes": {"bias": "15m", "structure": "5m", "entry": "1m"},
        "rules": [
            "underlying trend UPTREND/DOWNTREND on setup timeframe",
            "pullback detected: 1-3 counter-trend closes in last 5",
            "price within 0.5*ATR of EMA20 or S/R zone",
            "RSI recovering toward neutral (35-65 band)",
            "volatility NORMAL/HIGH; ADX>=20; ATR-ratio 0.4-2.0",
            "invalidation: structure break vs trend, regime flip to RANGE, pullback deeper than 61.8%, opposing sweep",
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
