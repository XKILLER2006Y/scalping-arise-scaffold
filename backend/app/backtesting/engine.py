"""Phase 9: event-driven backtest on candle list. Simplified SL/TP touch simulation."""
from app.market_data.models import Candle
from app.market_analysis.engine import analyze
from app.market_data.resample import resample, closed_asof
from app.technical_features.engine import compute_single_timeframe
from app.strategy.engine import evaluate_all
from app.signals.engine import decide
from app.trade_planning.engine import plan

def prepare_bars(candles: list[Candle], warmup: int = 200, window: int = 400) -> list[dict]:
    """Expensive part, done ONCE: per-bar analysis + features + strategy evaluations.

    Param-dependent steps (confidence threshold, SL/TP sizing, simulation) stay
    in run_backtest, so a 27-combo sensitivity grid costs 1x precompute + 27x cheap sims
    instead of 27x full pipelines.
    """
    bars: list[dict] = []
    htf5 = resample(candles, "5m")
    htf15 = resample(candles, "15m")
    for i in range(warmup, len(candles)):
        hist = candles[max(0, i + 1 - window):i + 1]
        ts = candles[i].timestamp
        a = analyze(hist, now_ts=ts)
        # HTF context from CLOSED resampled bars only (no look-ahead by construction).
        c5 = closed_asof(htf5, ts)
        c15 = closed_asof(htf15, ts)
        a5 = analyze(c5) if len(c5) >= 20 else None
        a15 = analyze(c15) if len(c15) >= 20 else None
        htf = {"bias": (a15 or a5 or a).model_dump(), "structure": (a5 or a).model_dump()}
        f = compute_single_timeframe(hist, "1m")
        feats = dict(f["features"])
        feats["volatility"] = f["volatility"]
        feats["rel_volume"] = f["features"].get("rel_volume")
        closes = [c.close for c in hist]
        evs = evaluate_all(a.model_dump(), feats, hist[-1].close, closes=closes,
                           candle_count=len(hist),
                           source_type=str(hist[0].source_type), mtf=htf)
        bars.append({"i": i, "entry": hist[-1].close, "atr": feats.get("atr14"),
                     "feats": feats, "evs": evs,
                     "ctx": {"session": a.session, "closes": closes[-10:],
                             "analysis": a.model_dump()}})
    return bars


def run_backtest(candles: list[Candle], equity: float = 10000.0, risk_pct: float = 1.0,
                 warmup: int = 200, horizon: int = 10, cost_per_trade: float = 0.3,
                 sl_mult: float = 1.5, tp_mult: float = 2.0, min_conf: int = 60,
                 return_all_trades: bool = False, window: int = 400,
                 prep: list[dict] | None = None) -> dict:
    trades: list[dict] = []
    equity_curve = [equity]
    cur = equity
    peak, max_dd = equity, 0.0
    bars = prep if prep is not None else prepare_bars(candles, warmup, window)
    cooldown_until = -1  # no stacking: one position per setup, re-arm after `horizon` bars
    for b in bars:
        i, entry, atr, feats, evs, ctx = (b["i"], b["entry"], b["atr"], b["feats"], b["evs"], b["ctx"])
        if i + horizon >= len(candles):
            continue
        if i < cooldown_until:
            continue  # post-trade cooldown: let the setup reset
        sig = decide(evs, feats, ctx, min_conf=min_conf)
        if sig["action"] == "NO_TRADE" or sig.get("state") not in ("CONFIRMED",):
            continue
        p = plan(sig, entry, atr, equity=cur, risk_pct=risk_pct,
                   sl_mult=sl_mult, tp_mult=tp_mult)
        if not p.get("feasible"):
            continue
        # simulate next `horizon` candles: SL/TP touch.
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
        pnl = r_mult * risk_money - cost_per_trade  # spread/commission drag + TIME exit at `horizon` bars
        cur += pnl
        equity_curve.append(cur)
        peak = max(peak, cur)
        max_dd = max(max_dd, (peak - cur) / peak * 100 if peak else 0)
        trades.append({"i": i, "strategy": sig["strategy"], "direction": direction,
                       "entry": entry, "exit": round(exit_px, 2), "r": round(r_mult, 2),
                       "pnl": round(pnl, 2), "result": res})
        cooldown_until = i + horizon
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gw = sum(t["pnl"] for t in wins); gl = -sum(t["pnl"] for t in losses)
    pf = (gw / gl) if gl else (float("inf") if gw else 0.0)
    wr = len(wins) / len(trades) if trades else 0.0
    exp = (sum(t["pnl"] for t in trades) / len(trades)) if trades else 0.0
    net = cur - equity
    gate, reasons = promotion_gate(len(trades), pf if pf != float("inf") else 99.0, max_dd)
    out = {"trades": len(trades), "wins": len(wins), "win_rate": round(wr, 3),
            "profit_factor": round(pf, 2) if pf != float("inf") else None,
            "expectancy": round(exp, 2), "net_pnl": round(net, 2),
            "max_drawdown_pct": round(max_dd, 2), "final_equity": round(cur, 2),
            "gate": gate, "gate_reasons": reasons, "sample": trades[:20]}
    if return_all_trades:
        out["trades_full"] = [{"pnl": t["pnl"]} for t in trades]
    return out

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
