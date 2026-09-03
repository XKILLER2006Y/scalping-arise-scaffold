"""Phase 10: full pipeline trace + health. Explainability first."""
import time
from app.market_analysis.engine import analyze
from app.technical_features.engine import compute_mtf
from app.strategy.engine import evaluate_all
from app.signals.engine import decide
from app.trade_planning.engine import plan as plan_trade
from app.intelligence.engine import is_blocked

_signal_counts: dict[str, int] = {"BUY": 0, "SELL": 0, "NO_TRADE": 0}
_forward_log: list[dict] = []

def _record_signal(action: str, state: str | None = None):
    _signal_counts[action] = _signal_counts.get(action, 0) + 1
    _forward_log.append({"t": int(time.time()), "action": action, "state": state})
    if len(_forward_log) > 500:
        del _forward_log[:len(_forward_log) - 500]

def reliability() -> dict:
    total = sum(_signal_counts.values())
    nt = _signal_counts.get("NO_TRADE", 0)
    return {"counts": dict(_signal_counts), "total": total,
            "no_trade_rate": round(nt / total, 3) if total else 0.0,
            "forward_logged": len(_forward_log)}

def full_trace(candles_1m, candles_5m, candles_15m, symbol="XAU/USD", equity=10000.0, risk_pct=1.0, spread=0.3) -> dict:
    t0 = time.time()
    mtf = compute_mtf({"1m": candles_1m, "5m": candles_5m, "15m": candles_15m}, symbol)
    entry_tf = mtf["timeframes"]["1m"]
    a = analyze(candles_1m, symbol)
    feats = dict(entry_tf["features"]); feats["volatility"] = entry_tf["volatility"]
    evs = evaluate_all(a.model_dump(), feats, candles_1m[-1].close if candles_1m else None)
    sig = decide(evs, feats)
    news = is_blocked()
    if news["blocked"] and sig["action"] != "NO_TRADE":
        sig = {"action": "NO_TRADE", "strategy": None, "direction": None, "confidence": 0,
               "quality": 0, "state": "BLOCKED_NEWS", "reasons": [news["reason"]]}
    trade = plan_trade(sig, candles_1m[-1].close if candles_1m else 0, feats.get("atr14"), equity, risk_pct, spread) if candles_1m else {"feasible": False}
    _record_signal(sig.get("action", "NO_TRADE"), sig.get("state"))
    return {"symbol": symbol, "market": a.model_dump(), "features_mtf": mtf,
            "evaluations": evs, "signal": sig, "news": news, "trade_plan": trade,
            "latency_ms": round((time.time() - t0) * 1000, 1),
            "disclaimer": "Analysis only. Not financial advice."}

def system_health() -> dict:
    from app.market_data.service import _provider_health
    return {"status": "ok", "modules": ["market_data", "market_analysis", "technical_features",
                                        "strategy", "signals", "trade_planning", "intelligence", "backtesting"],
            "providers": _provider_health, "reliability": reliability(), "timestamp": int(time.time())}
