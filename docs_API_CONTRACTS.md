# API Contracts (scaffold — verified from code)

## Health
- GET /api/v1/health → {status, app, phase}
- GET /api/v1/system/health → modules, providers, timestamp

## Phase 2 Market Data
- GET /api/v1/market-data/health → {status, module, providers{twelve_data,yfinance}}
- GET /api/v1/market-data/capabilities
- GET /api/v1/market-data/candles?symbol=XAU/USD&timeframe=1m&limit=100 → {meta{source,source_type,failover,fresh,cached}, candles[Candle]}
- GET /api/v1/market-data/latest?symbol&timeframe → {meta, candle}
- Candle: {timestamp,open,high,low,close,volume,symbol,canonical_instrument,provider_instrument,source,source_type SPOT|FUTURES_PROXY}

## Phase 3 Market Analysis
- GET /api/v1/market-analysis/health, /capabilities
- POST /api/v1/market-analysis {symbol, candles} → {trend, regime, session, swings_high/low, bos, choch, support, resistance, source_type, candle_count}

## Phase 4 Technical Features (+extension)
- GET /api/v1/technical-features/health, /capabilities
- POST /api/v1/technical-features?timeframe=1m {symbol, candles} → {symbol,timeframe,features{ema20/50/200,rsi14,macd_*,atr14,bb_*,vol_*,price_*},volatility,atr_pct,status READY|WARMING_UP|UNAVAILABLE,reason,source_type,candle_count}
- POST /api/v1/technical-features/mtf {symbol, candles_by_timeframe:{1m,5m,15m}} → {symbol, timeframes{...}}

## Phase 5 Strategy
- GET /api/v1/strategy/health, /capabilities
- POST /api/v1/strategy/evaluate {analysis, features, close} → {evaluations[{strategy,direction,qualified,quality,met,missing}]}

## Phase 6 Signals
- GET /api/v1/signals/health
- POST /api/v1/signals/decide {evaluations, features} → {action BUY|SELL|NO_TRADE, strategy, direction, confidence, quality, state, reasons}

## Phase 7 Trade Plan
- GET /api/v1/trade-plan/health
- POST /api/v1/trade-plan {signal, entry, atr, equity, risk_pct, spread} → {feasible, entry, stop, take_profit, rr, lots, spread_ok, reasons}

## Phase 8 Intelligence
- GET /api/v1/intelligence/health, /news-check, /strategy/{name}
- POST /api/v1/intelligence/record {strategy, pnl}

## Phase 9 Backtest
- GET /api/v1/backtest/health
- POST /api/v1/backtest/run {candles, equity, risk_pct} → {trades, win_rate, profit_factor, expectancy, max_drawdown_pct, gate PROMOTE|WAIT|REJECT}

## Phase 10 System
- POST /api/v1/system/trace {symbol, candles_1m, candles_5m, candles_15m, equity, risk_pct, spread} → {market, features_mtf, evaluations, signal, news, trade_plan, latency_ms}
