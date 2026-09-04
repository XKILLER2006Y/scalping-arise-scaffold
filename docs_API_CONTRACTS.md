# API Contracts (scaffold — verified from code)

## Health
- GET /api/v1/health → {status, app, phase}
- GET /api/v1/system/health → modules, providers, reliability, timestamp
- GET /api/v1/system/metrics → {uptime_s, reliability, providers}

## Phase 2 Market Data
- GET /api/v1/market-data/health → {status, module, providers{twelve_data,yfinance}}
- GET /api/v1/market-data/capabilities
- GET /api/v1/market-data/candles?symbol=XAU/USD&timeframe=1m&limit=100 → {meta{source,source_type,failover,fresh,cached}, candles[Candle]}
- GET /api/v1/market-data/latest?symbol&timeframe → {meta, candle}
- Candle: {timestamp,open,high,low,close,volume,symbol,canonical_instrument,provider_instrument,source,source_type SPOT|FUTURES_PROXY}

## Phase 3 Market Analysis
- GET /api/v1/market-analysis/health, /capabilities
- POST /api/v1/market-analysis {symbol, candles} → {trend, regime, session, swings_high/low, bos, choch, support, resistance, sweeps[SSL/BSL], fvgs[BULL/BEAR], source_type, candle_count}

## Phase 4 Technical Features (+extension)
- GET /api/v1/technical-features/health, /capabilities
- POST /api/v1/technical-features?timeframe=1m {symbol, candles} → {symbol,timeframe,features{ema20/50/200,rsi14,macd_*,atr14,atr_ratio,z20,adx14,vwap,bb_*,vol_*,price_*},volatility,atr_pct,status READY|WARMING_UP|UNAVAILABLE,reason,source_type,candle_count}
- POST /api/v1/technical-features/mtf {symbol, candles_by_timeframe:{1m,5m,15m}} → {symbol, timeframes{...}}

## Phase 5 Strategy
- GET /api/v1/strategy/health, /capabilities
- POST /api/v1/strategy/evaluate {analysis, features, close} → {evaluations[{strategy,direction,qualified,quality,met,missing}]} (gates: ADX, ATR-ratio 0.4-2.0, |Z|>=2 for fade)

## Phase 6 Signals
- GET /api/v1/signals/health
- POST /api/v1/signals/decide {evaluations, features, context{session,closes,analysis}} → {action BUY|SELL|NO_TRADE, strategy, direction, confidence, quality, state PROPOSED|ARMED|CONFIRMED|REJECTED|CONFLICT, reasons}

## Phase 7 Trade Plan
- GET /api/v1/trade-plan/health
- POST /api/v1/trade-plan {signal, entry, atr, equity, risk_pct, spread} → {feasible, entry, stop, take_profit, rr, lots, spread_ok, cost_ok, multi_tp[TP1 1.5R/TP2 2.5R/TP3 4R], reasons}

## Phase 8 Intelligence
- GET /api/v1/intelligence/health, /news-check, /exposure, /strategy/{name}
- POST /api/v1/intelligence/record {strategy, pnl} (daily cap 10 trades, -5% halt, 2-loss 30m cooldown)

## Phase 9 Backtest
- GET /api/v1/backtest/health
- POST /api/v1/backtest/run {candles, equity, risk_pct} → {trades, win_rate, profit_factor, expectancy, max_drawdown_pct, gate PROMOTE|WAIT|REJECT} (10-bar time exit + cost drag)

## Phase 10 System
- POST /api/v1/system/trace {symbol, candles_1m, candles_5m, candles_15m, equity, risk_pct, spread} → {market, features_mtf, evaluations, signal, news, exposure, trade_plan, latency_ms}
- GET /api/v1/system/reliability → {counts, total, no_trade_rate, forward_logged}
- GET /api/v1/system/forward?limit=50 → {entries, total}

## Production
- backend/Dockerfile, frontend/Dockerfile, docker-compose.yml (8000 + 3000)
- .github/workflows/ci.yml (pytest + next build)

## Research applied (internet round)
- Killzone sessions LONDON/NEW_YORK gate; ASIA/OFF review-only
- ARMED pullback 1-3/5 bars before trend entry (4-phase state machine)
- Liquidity sweep + FVG detectors, sweep confluence boost
- Z-score>=2 + ADX<=22 fade filter; ADX>=20 + ATR-ratio 0.4-2.0 trend filter
- Cost gate TP>=4x cost, ATR>=3x cost; multi-TP ladder + breakeven note
- Daily 10-trade cap, -5% halt, 2-loss cooldown; VWAP context

## Friend-port additions (w/ permission, see ATTRIBUTION.md)
- Strategy `PULLBACK_CONT` in POST /api/v1/strategy/evaluate (3 evaluations now)
- Each evaluation carries `eligibility` (gate: analysis/candles/features/source/regime)
  and `invalidation` (veto rules: CHOCH, regime flip, structure break, >61.8% depth,
  breakout, opposing sweep, sweep acceptance)
- GET /api/v1/strategy/evaluate-quick?symbol&timeframe&limit (server-side fetch)
- GET /api/v1/system/trace-quick?symbol&limit&equity&risk_pct&spread
- Market-data cache is LRU (32 entries) + TTL, thread-safe

## Wave 1 validation
- POST /api/v1/validation/walk-forward {candles, folds, grid?} → IS-select → OOS test per fold + wf_efficiency
- POST /api/v1/validation/monte-carlo {candles} → trade shuffle 1000x: P(negative), p5 net, p95 DD
- POST /api/v1/validation/sensitivity {candles, grid?} → sl×tp×conf grid + CLIFF_RISK/STABLE verdict
- POST /api/v1/validation/full-audit {candles, folds, grid?} → base + WF + MC + sensitivity + 30%-of-B&H benchmark → PROMOTE/WAIT/REJECT
