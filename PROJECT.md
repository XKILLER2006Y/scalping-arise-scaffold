# Project: Scalping Arise Audit & Bug Resolution

## Architecture
- **Backend**: FastAPI with Python 3.13, modular domain architecture under `backend/app/`:
  - `core`: Config (`pydantic-settings`), SQLite persistence (`scalping.db`), middleware (`request_id_log`, `guard`), logging, security.
  - `market_data`: Models (`Candle`, `SourceType`), providers (`TwelveDataProvider`, `YFinanceProvider`, `synth_candles`, `synth_websocket_stream`), caching and validation.
  - `market_analysis`: Swings, liquidity sweeps, FVGs, trend classification (`AnalysisResult`).
  - `technical_features`: EMA, RSI, MACD, ATR, Bollinger Bands, single/multi-timeframe engines.
  - `strategy`: Strategy rules (`TREND_CONT`, `RANGE_FADE`), qualification engine.
  - `signals`: Signal state machine (`decide`), session/killzone gate, confirmation.
  - `trade_planning`: Sizing, SL/TP calculation, Kelly sizing, cost gate (`create_plan` / `plan`).
  - `intelligence`: High-impact news guard, daily exposure limits, XGBoost / sentiment heuristics.
  - `backtesting`: Event-driven simulation (`run_backtest`), promotion gate.
  - `system`: End-to-end trace (`full_trace`), reliability counters.
  - `execution`: Paper broker (`PaperBroker`), portfolio state, order execution.
  - `main.py`: App factory, router mounts, background `auto_trade_loop()`, lifespan.
- **Frontend**: Next.js 14.2 (App Router), React 18, TypeScript, `lightweight-charts: ^5.2.1`:
  - `app/page.tsx`: Single-page trading bot dashboard, step-by-step runner, full pipeline trace.
  - `components/Chart.tsx`: Candlestick series, volume histogram, signal buy/sell markers.
  - `lib/api.ts`: Typed REST API client targeting FastAPI backend.

## Feature & Bug Inventory
Every feature and bug identified during Phase 0 Survey:
| # | Item / Bug | Description | Milestone | Source |
|---|------------|-------------|-----------|--------|
| 1 | Plan Function Import Error | `trade_planning/engine.py` defines `create_plan` without `plan` alias, breaking routers and pytest collection across all 6 test suites | M1 | survey (backend/tests) |
| 2 | Market Analysis Import Error | `main.py` imports `analyze_market` from `market_analysis/engine.py` where function is `analyze` | M1 | survey (backend/loop) |
| 3 | Execution Broker Schema Mismatch | `PaperBroker.execute_trade` expects `entry_price`, `direction`, `stop_loss`, `take_profit_1`, `position_size` while `trade_planning` returns `entry`, `stop`, `take_profit`, `lots` | M1 | survey (backend) |
| 4 | Phantom Trade Execution on NO_TRADE | `PaperBroker.execute_trade` checks `plan.get("action") == "NO_TRADE"`; because plan lacks `"action"`, it executes phantom orders with hardcoded default prices | M1 | survey (backend) |
| 5 | Broker Concurrency Race Condition | `PaperBroker` singleton shared between asyncio event loop and FastAPI sync routes (AnyIO threadpool) lacks thread safety lock | M1 | survey (backend/loop) |
| 6 | Market Data Cache Poisoning & Inverted Slicing | `get_candles` caches single candle on `limit=1` poisoning subsequent calls; uses `[:limit]` (oldest) instead of `[-limit:]` (newest) | M1 | survey (backend) |
| 7 | Sentiment Indicator Comparison TypeError | Comparing float with NoneType on uninitialized indicator values (`ema200`, `rsi14`) raises TypeError | M1 | survey (backend) |
| 8 | Execution Router Close All 422 Error | `POST /close_all` expects `current_price` as query parameter instead of accepting JSON body | M1 | survey (backend) |
| 9 | AnalysisResult AttributeError in Auto-Trade Loop | `main.py` passes Pydantic `AnalysisResult` directly to `evaluate_all` which calls `.get()`, raising AttributeError | M2 | survey (backend/loop) |
| 10 | Volatility Feature Dropped in Auto-Trade Loop | `main.py` passes `feats["features"]` without `_volatility`, preventing strategy rules from qualifying | M2 | survey (backend/loop) |
| 11 | Wrong Argument in compute_features Call | `main.py` calls `compute_features(history[-220:], "1m")` passing timeframe where symbol is expected | M2 | survey (backend/loop) |
| 12 | KeyError 'action' in Auto-Trade Loop | `main.py` accesses `plan["action"]` which is missing from plan dictionary | M2 | survey (backend/loop) |
| 13 | Auto-Trade Loop Fatal Termination on Tick Error | Outer try-except wraps entire loop, causing permanent coroutine termination on any transient error | M2 | survey (backend/loop) |
| 14 | Starlette Middleware LIFO Ordering | `guard` registered after `request_id_log` runs first, preventing request ID / latency headers on rejected requests | M2 | survey (backend) |
| 15 | Unhandled Task Cancellation in Lifespan | `task.cancel()` in lifespan is not awaited or caught, risking unhandled cancellation during shutdown | M2 | survey (backend/loop) |
| 16 | Frontend TS2741 on page.tsx:37 | `let exec = { status: "skipped" }` inferred type incompatible with `{}` return from `api.execute(pl)` | M3 | survey (frontend) |
| 17 | Lightweight Charts v5 Incompatibility | `addCandlestickSeries`, `addHistogramSeries`, and `setMarkers` removed in v5.2.1 | M3 | survey (frontend) |
| 18 | Ghost SELL Markers for NO_TRADE | `Chart.tsx` falls back to downward red arrow for neutral / NO_TRADE signals | M3 | survey (frontend) |
| 19 | Infeasible Trade Execution in Frontend | `app/page.tsx:37` checks `pl.action !== "NO_TRADE"` (undefined) and passes incompatible payload to broker | M3 | survey (frontend) |
| 20 | Chart Re-render Flicker | Unused `features` prop in `Chart.tsx` `useEffect` dependencies causes continuous chart canvas recreation | M3 | survey (frontend) |
| 21 | Full Pipeline Signal Desync & Null Safety | `fullPipeline` omits signals update; missing null checks on market data candle responses | M3 | survey (frontend) |
| 22 | Comprehensive E2E Verification & Hardening | Verify full pytest suite passes, npm run build passes, auto_trade_loop runs cleanly, forensic audit passes | M4 | acceptance criteria |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | M1: Backend Core, Market Data, Trade Planning & Execution | Items 1, 2, 3, 4, 5, 6, 7, 8 | none | DONE |
| 2 | M2: Auto-Trading Loop & Lifecycle Hardening | Items 9, 10, 11, 12, 13, 14, 15 | M1 | DONE |
| 3 | M3: Frontend Next.js Build & UI Bug Resolution | Items 16, 17, 18, 19, 20, 21 | none | DONE |
| 4 | M4: E2E Acceptance Verification & Integrity Forensics | Item 22: Pytest 100%, npm run build 100%, auto_trade_loop test, forensic audit | M1, M2, M3 | DONE |

## Interface Contracts
### Trade Planning ↔ Execution
- `trade_planning.engine.create_plan` / `plan` produces:
  ```python
  {
      "feasible": bool,
      "entry": float,
      "stop": float,
      "take_profit": float,
      "lots": float,
      "action": str,  # ("BUY", "SELL", or "NO_TRADE" derived from signal["action"])
      "direction": str | None,  # ("LONG", "SHORT", or None derived from signal["direction"])
      "signal": dict,
      "reason": str | None,
      ...
  }
  ```
- `PaperBroker.execute_trade` accepts both snake_case legacy format (`entry_price`, `direction`, `stop_loss`, `take_profit_1`, `position_size`) and plan dictionary format (`entry`, `direction`, `stop`, `take_profit`, `lots`). It rejects infeasible or NO_TRADE plans without creating phantom positions.

### Market Analysis ↔ Strategy Evaluation
- `market_analysis.engine.analyze` returns `AnalysisResult`.
- Both `analyze` and `analyze_market` alias are exported.
- `strategy.engine.evaluate_all` accepts either `dict` or `AnalysisResult` (calling `.model_dump()` if Pydantic model).

### Technical Features ↔ Strategy Evaluation
- `compute_features` returns `{"features": {...}, "volatility": "...", ...}`.
- Strategy evaluators check both `feats.get("volatility")` and `feats.get("_volatility")` ensuring no dropped qualifications.

## Code Layout
- Exclusive write ownership per milestone:
  - M1: `backend/app/trade_planning/`, `backend/app/market_analysis/`, `backend/app/market_data/`, `backend/app/intelligence/`, `backend/app/execution/`
  - M2: `backend/app/main.py`, `backend/tests/test_auto_trade_loop.py`
  - M3: `frontend/app/page.tsx`, `frontend/components/Chart.tsx`, `frontend/lib/api.ts`
  - M4: `backend/tests/` (verification only, no modifications to core logic)
