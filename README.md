# Scalping Arise — Scaffold (ours, compare later with friend's repo)

Modular XAU/USD trading analysis platform. Scaffold-only full pipeline.

## Current Status (scaffold — COMPLETE)
```
Phase 1: Complete
Phase 2: Complete (live Twelve Data SPOT + yfinance GC=F FUTURES_PROXY, retries, cache, failover, freshness, gaps)
Phase 3: Complete
Phase 4 Core + Extension: Complete (MTF 1m/5m/15m, volatility, READY/WARMING_UP/UNAVAILABLE)
Phase 5 Strategy: Complete (TREND_CONT + RANGE_FADE evaluation)
Phase 6 Signals: Complete (BUY/SELL/NO_TRADE, confidence vs quality, conflict resolver)
Phase 7 Trade Plan: Complete (1.5xATR SL, 2R TP, RR, sizing, spread check — plan only)
Phase 8 Intelligence: Complete (news blackout + PF/WR kill-switch)
Phase 9 Backtest: Complete (metrics + PROMOTE/WAIT/REJECT gate)
Phase 10 System: Complete (trace + health)
```

> Friend's real repo stays joint-locked. This is our independent reference for later comparison.

## Architecture
```
Market Data -> Structure/Regime -> Features MTF -> Strategy Eval -> Signal Decide -> Trade Plan -> Intel/News -> Backtest -> Trace/Health
```

## Structure
```
backend/app/main.py — factory v0.10.0-scaffold
backend/app/core/, market_data/, market_analysis/, technical_features/
backend/app/strategy/, signals/, trade_planning/, intelligence/, backtesting/, system/
frontend/app/page.tsx + layout.tsx, frontend/lib/api.ts — full pipeline dashboard
docs_API_CONTRACTS.md — endpoint inventory
docs_PHASE4_EXTENSION_PROPOSAL.md — original proposal
```

## Prerequisites
Python 3.11+, Node 18+

## Backend Setup
```bash
cd /home/arifureta/Desktop/scalping-arise-scaffold
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python -m uvicorn app.main:app --app-dir backend --port 8000
# live data: set backend/.env SCALPING_ARISE_TWELVE_DATA_API_KEY=... (else demo-synthetic SPOT)
```

## Frontend Setup
```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev  # or npm run build && npm start
```

## Testing
```bash
.venv/bin/python -m pytest backend/tests -q  # 15 tests
```

## API Overview
See docs_API_CONTRACTS.md. Key: /health, /market-data/*, /market-analysis, /technical-features + /mtf, /strategy/evaluate, /signals/decide, /trade-plan, /intelligence/*, /backtest/run, /system/trace + /health

## Data Source Warning
- Twelve Data XAU/USD = SPOT
- yfinance GC=F = FUTURES_PROXY — never equal to spot. source_type preserved end-to-end.

## Development Rules
- Phase 4 describes, never decides. Decisions live in Phase 6+ only.
- No look-ahead: only closed candles per TF.
- Analysis only. Not financial advice.
