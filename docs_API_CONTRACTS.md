# XAU/USD Signal Bot — API

One call does everything: `GET /api/v1/signal?symbol=XAU/USD&limit=250`
→ past + live market data in, `{signal: {action BUY|SELL|NO_TRADE, confidence, quality, strategy, reasons}, trade_plan: {entry, stop, take_profit, rr}, market, features_mtf, evaluations}` out.

## Layers (signals only — no execution anywhere)

- `GET /api/v1/health`, `/api/v1/system/health`, `/api/v1/system/metrics`
- Market data: `/api/v1/market-data/health|candles|latest|capabilities`
  (Twelve Data XAU/USD SPOT → yfinance GC=F FUTURES_PROXY fallback; source preserved)
- Analysis: `POST /api/v1/market-analysis` → trend/regime/session/swings/BOS/sweeps/FVGs
- Features: `POST /api/v1/technical-features[?timeframe]` + `/mtf`
  (EMA/RSI/MACD/ATR/Z/ADX/VWAP/BB, MTF 1m/5m/15m, adaptive volatility, READY/WARMING_UP/UNAVAILABLE)
- Strategy: `POST /api/v1/strategy/evaluate`, `GET /api/v1/strategy/evaluate-quick`
  (TREND_CONT, PULLBACK_CONT, RANGE_FADE + eligibility gate + invalidation vetoes)
- Signals: `POST /api/v1/signals/decide` (killzone sessions, ARMED pullback, sweep confluence, conflict resolver)
- Trade plan (signal enrichment): `POST /api/v1/trade-plan` → entry/SL/TP/RR/sizing/cost gate/multi-TP. Plan only.
- Intelligence: `/api/v1/intelligence/news-check|exposure|strategy/{name}`, `POST /record`
- Proof: `POST /api/v1/backtest/run`, `/api/v1/validation/{walk-forward,monte-carlo,sensitivity,full-audit}`
- Signal log: `/api/v1/system/trace`, `/trace-quick`, `/reliability`, `/forward`

## Design rules

- HTF bias (15m) → structure (5m) → entry (1m). Never fade HTF trend.
- Killzones LONDON/NEW_YORK confirm; ASIA/OFF review-only.
- Closed candles only, all timeframes. No look-ahead.
- Signals only. Not financial advice.

## Market data providers (primary first)
- TradingView OANDA:XAUUSD SPOT (primary, no key — unofficial feed, auto-failover below)
- Twelve Data XAU/USD SPOT (keyed via TWELVE_DATA_API_KEY)
- yfinance GC=F FUTURES_PROXY (last resort, honestly labeled)
