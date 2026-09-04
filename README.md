# XAU/USD Signal Bot

Past + live market data in — **BUY / SELL / NO_TRADE** out. Nothing else.
No execution, no brokers, no auto-trading, no ML baggage.

## How it works

```
Twelve Data XAU/USD SPOT (yfinance GC=F fallback, labeled FUTURES_PROXY)
  → Market structure (swings, BOS/CHOCH, sweeps, FVGs, sessions, regimes)
  → MTF features 1m/5m/15m (EMA/RSI/MACD/ATR/Z/ADX/VWAP/BB, adaptive volatility)
  → 3 strategies (trend-continuation, pullback-continuation, range-fade)
    + eligibility gate + invalidation vetoes
  → Signal decision (killzone sessions, pullback states, conflict resolver)
  → Entry/SL/TP/RR plan + news/exposure filters
```

One call: `GET /api/v1/signal?symbol=XAU/USD`

## Run

```bash
cd backend && ../.venv/bin/python -m uvicorn app.main:app --app-dir . --port 8000
cd frontend && npm install && npm run dev   # http://localhost:3000
```

```bash
.venv/bin/python -m pytest backend/tests -q
```

## Proof, not promises

`POST /validation/full-audit` — walk-forward + Monte Carlo + sensitivity grid +
30%-of-B&H benchmark → PROMOTE/WAIT/REJECT. Latest real-data trials: WAIT then
REJECT. The bot reports its own report card; read it before trusting any signal.

## Rules

- HTF bias → structure → entry. Never fade the higher-timeframe trend.
- LONDON/NEW_YORK confirm; ASIA/OFF review-only.
- Closed candles only. No look-ahead. Source identity preserved end to end.
- Signals only. Not financial advice.
