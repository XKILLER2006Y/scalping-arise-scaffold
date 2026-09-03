# Phase 4 Extension — Proposal Only (no code yet)

Strict scope: MTF 1m/5m/15m + volatility class + READY/WARMING_UP/UNAVAILABLE + reason.
No BUY/SELL/NO-TRADE, no confirmation logic.

## Proposed response shape
```json
{
  "symbol": "XAU/USD",
  "timeframe": "5m",
  "features": {
    "ema20": 2651.2, "ema50": 2649.8, "rsi14": 58.1,
    "atr14": 2.4, "bb_mid": 2650.0
  },
  "volatility": "NORMAL_VOLATILITY",
  "status": "READY",
  "reason": null,
  "source_type": "SPOT",
  "provider_instrument": "XAU/USD",
  "timestamp": 1234567890
}
```

## Rules
- Compute each TF independently, no cross-TF decision here.
- Volatility from ATR% = ATR14 / close, thresholds from central config (env-overridable).
  - < vol_low_max → LOW, < vol_normal_max → NORMAL, < vol_high_max → HIGH, else EXTREME
- Status:
  - UNAVAILABLE: no candles / provider fail / invalid
  - WARMING_UP: n < max_period (e.g. 200 for EMA200) — include reason like "need 200 candles, have 80"
  - READY: all required features computed
- Volume optional: missing volume must not fail other features.
- Preserve source_type per TF.
