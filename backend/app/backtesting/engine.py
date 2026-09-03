"""Phase 9: event-driven backtest on candle list. Simplified SL/TP touch simulation."""
from app.market_data.models import Candle
from app.market_analysis.engine import analyze
from app.technical_features.engine import compute_single_timeframe
from app.strategy.engine import evaluate_all
from app.signals.engine import decide
from app.trade_planning.engine import plan

def run_backtest(candles: list[Candle], equity: float = 10000.0, risk_pct: float = 1.0,
                 warmup: int = 200, horizon: int = 10) -> dict:
    trades: list[dict] = []
    equity_curve = [equity]
    cur = equity
    peak, max_dd = equity, 0.0
    for i in range(warmup, len(candles) - horizon):
        window = candles[:i + 1]
        a = analyze(window)
        f = compute_single_timeframe(window, "1m")
        feats = dict(f["features"]); feats["volatility"] = f["volatility"]; feats["rel_volume"] = f["features"].get("rel_volume")
        evs = evaluate_all(a.model_dump(), feats, window[-1].close)
        sig = decide(evs, feats)
        if sig["action"] == "NO_TRADE" or sig.get("state") != "CONFIRMED":
            continue
        p = plan(sig, window[-1].close, feats.get("atr14"), equity=cur, risk_pct=risk_pct)
        if not p.get("feasible"):
            continue
        # simulate next `horizon` candles: SL/TP touch?
        entry, sl, tp = p["entry"], p["stop"], p["take_profit"]
        direction = sig["direction"]
        exit_px, res = None, "TIME"
        for k in range(i + 1, min(i + 1 + horizon, len(candles))):
            h, l = candles[k].high, candles[k].low
            if direction == "LONG":
                if l <= sl:
                    exit_px, res = sl, "SL"; break
                if h >= tp:
                    exit_px, res = tp, "TP"; break
            else:
                if h >= sl:
                    exit_px, res = sl, "SL"; break
                if l <= tp:
                    exit_px, res = tp, "TP"; break
        if exit_px is None:
            exit_px = candles[min(i + horizon, len(candles) - 1)].close
        gross = (exit_px - entry) if direction == "LONG" else (entry - exit_px)
        risk_dist = abs(entry - sl) or 1e-9
        r_mult = gross / risk_dist
        risk_money = cur * risk_pct / 100.0
        pnl = r_mult * risk_money
        cur += pnl
        equity_curve.append(cur)
        peak = max(peak, cur)
        max_dd = max(max_dd, (peak - cur) / peak * 100 if peak else 0)
        trades.append({"i": i, "strategy": sig["strategy"], "direction": direction,
                       "entry": entry, "exit": round(exit_px, 2), "r": round(r_mult, 2),
                       "pnl": round(pnl, 2), "result": res})
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gw = sum(t["pnl"] for t in wins); gl = -sum(t["pnl"] for t in losses)
    pf = (gw / gl) if gl else (float("inf") if gw else 0.0)
    wr = len(wins) / len(trades) if trades else 0.0
    exp = (sum(t["pnl"] for t in trades) / len(trades)) if trades else 0.0
    net = cur - equity
    gate, reasons = promotion_gate(len(trades), pf if pf != float("inf") else 99.0, max_dd)
    return {"trades": len(trades), "wins": len(wins), "win_rate": round(wr, 3),
            "profit_factor": round(pf, 2) if pf != float("inf") else None,
            "expectancy": round(exp, 2), "net_pnl": round(net, 2),
            "max_drawdown_pct": round(max_dd, 2), "final_equity": round(cur, 2),
            "gate": gate, "gate_reasons": reasons, "sample": trades[:20]}

def promotion_gate(n: int, pf: float, max_dd: float) -> tuple[str, list[str]]:
    reasons = []
    if n < 50:
        reasons.append(f"only {n} trades (<50 minimum)")
    if pf < 1.5:
        reasons.append(f"PF {pf:.2f} < 1.5")
    if max_dd > 25:
        reasons.append(f"DD {max_dd:.1f}% > 25%")
    if not reasons:
        return "PROMOTE", ["meets PF>=1.5, DD<=25%, n>=50"]
    if n < 20 or pf < 1.0:
        return "REJECT", reasons
    return "WAIT", reasons
