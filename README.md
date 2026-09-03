# Scalping Arise — Scaffold (interim, until friend shares real repo)

Modular XAU/USD trading analysis platform. This scaffold mirrors Phases 1-4 CORE only.

## Current Status
```
Phase 1: Complete
Phase 2: Complete and Corrected
Phase 3: Complete
Phase 4 Core: Complete
Phase 4 Extension: Planned / Not Yet Implemented
Phase 5-10: Planned
```

## Architecture
```
Market Data -> Market Structure & Regime -> Technical Features -> [STOP]
Strategy / Signals / Risk / News / Backtest: NOT IMPLEMENTED
```

## Structure
```
backend/app/main.py — factory, CORS, versioned API
backend/app/core/ — config, logging, errors
backend/app/market_data/ — providers (twelve_data SPOT, yfinance GC=F FUTURES_PROXY), service (validate/cache/failover/freshness/gaps), router
backend/app/market_analysis/ — swings, trend, BOS/CHOCH, S/R, session, regime
backend/app/technical_features/ — EMA20/50/200, RSI14, MACD, ATR14, BB20, VolSMA20, price features
frontend/app/page.tsx — health verification only
docs/PHASE4_EXTENSION_PROPOSAL.md — schema proposal, no code
```

## Prerequisites
Python 3.11+, Node 18+ (frontend optional)

## Backend Setup (source of truth)
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

## Frontend Setup
```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

## Testing
```bash
cd backend
pytest -q
```

## API Overview
```
/api/v1/health
/api/v1/market-data/health, /capabilities, /candles, /latest
/api/v1/market-analysis/health, /capabilities, POST /api/v1/market-analysis
/api/v1/technical-features/health, /capabilities, POST /api/v1/technical-features
```

## Data Source Warning
- Twelve Data XAU/USD = SPOT
- yfinance GC=F = FUTURES_PROXY
- Never treat GC=F == spot. `source_type`, `provider_instrument`, `canonical_instrument` preserved end-to-end.

## Development Rules
- Do not mix phases. Phase 4 describes, never decides.
- No look-ahead bias. No BUY/SELL/NO-TRADE before Phase 6.
- Preserve source metadata. No secrets in git. Add tests. Run regression.
