"""Wave 1 validation: walk-forward, Monte Carlo, sensitivity, benchmark gate.

Answers the internet's #1 question — "was it edge or curve-fit?" — with:
- Walk-forward: in-sample param select -> out-of-sample test, rolling folds.
  Reports WF efficiency = OOS PF / IS PF (collapses toward 0 when overfit).
- Monte Carlo: shuffle trade order 1000x -> net/DD distribution, P(net<0).
- Sensitivity: grid over sl_mult x tp_mult x min_conf -> stable-range check.
- Benchmark gate: strategy net must clear 30% of buy-and-hold (advisory bar
  from live fleet practice) or beat it outright when B&H is negative.
"""
from __future__ import annotations
import random
from app.market_data.models import Candle
from app.backtesting.engine import run_backtest, prepare_bars

PARAM_GRID = {
    "sl_mult": [1.0, 1.5, 2.0],
    "tp_mult": [1.5, 2.0, 2.5],
    "min_conf": [50, 60, 70],
}


def _pf_of(res: dict) -> float:
    pf = res.get("profit_factor")
    return float(pf) if pf is not None else 0.0


def walk_forward(candles: list[Candle], folds: int = 3, equity: float = 10000.0,
                 risk_pct: float = 1.0, warmup: int = 200, grid: dict | None = None) -> dict:
    grid = grid or PARAM_GRID
    n = len(candles)
    fold_rows: list[dict] = []
    oos_trades: list[dict] = []
    for f in range(folds):
        # Expanding in-sample, rolling OOS slice.
        is_end = int(n * (0.5 + 0.15 * f))
        oos_end = int(n * (0.65 + 0.15 * f)) if f < folds - 1 else n
        is_c = candles[:is_end]
        oos_c = candles[is_end:oos_end]
        if len(is_c) <= warmup + 10 or len(oos_c) < 20:
            continue
        best, best_pf = None, -1.0
        is_prep = prepare_bars(is_c, warmup)
        for sl in grid["sl_mult"]:
            for tp in grid["tp_mult"]:
                for mc in grid["min_conf"]:
                    r = run_backtest(is_c, equity, risk_pct, warmup, 10, 0.3, sl, tp, mc, prep=is_prep)
                    pf = _pf_of(r)
                    if r["trades"] >= 5 and pf > best_pf:
                        best, best_pf = (sl, tp, mc), pf
        if best is None:
            continue
        oos = run_backtest(oos_c, equity, risk_pct, warmup, 10, 0.3, *best,
                                prep=prepare_bars(oos_c, warmup))
        # Collect OOS trade pnls for Monte Carlo.
        oos_trades.extend(oos.get("sample", []))
        eff = (_pf_of(oos) / best_pf) if best_pf > 0 else 0.0
        thin = oos["trades"] < 5
        fold_rows.append({"fold": f, "is_pf": round(best_pf, 2), "params": best,
                          "oos_trades": oos["trades"], "oos_pf": round(_pf_of(oos), 2),
                          "oos_net": oos["net_pnl"], "wf_efficiency": round(eff, 2),
                          "thin": thin})
    solid = [r for r in fold_rows if not r["thin"]]
    passing = [r for r in solid if r["wf_efficiency"] >= 0.4]
    avg_eff = round(sum(r["wf_efficiency"] for r in solid) / len(solid), 2) if solid else 0.0
    # Consistency gate: average hides bimodal folds (one great, two dead).
    # Need >=2 solid folds AND >=2 passing AND avg>=0.5.
    if len(solid) >= 2 and len(passing) >= 2 and avg_eff >= 0.5:
        verdict = "ROBUST"
    elif not fold_rows:
        verdict = "NO_DATA"
    elif len(solid) < 2:
        verdict = "INSUFFICIENT_DATA"
    else:
        verdict = "WEAK"
    return {"folds": fold_rows, "avg_wf_efficiency": avg_eff, "verdict": verdict,
            "note": "ROBUST needs >=2 solid (>=5-trade OOS) folds, >=2 with eff>=0.4, avg>=0.5"}


def monte_carlo(trade_pnls: list[float], sims: int = 1000, seed: int = 7,
                equity: float = 10000.0) -> dict:
    """Order-shuffle Monte Carlo. Net total is order-invariant, so this measures
    PATH risk: max-drawdown and losing-streak distributions across orderings."""
    rng = random.Random(seed)
    if not trade_pnls:
        return {"sims": 0, "p_bad_path": None, "p95_max_dd_pct": None,
                "median_max_dd_pct": None, "p95_max_consec_losses": None,
                "verdict": "NO_TRADES"}
    bad, dds, streaks = 0, [], []
    for _ in range(sims):
        order = trade_pnls[:]
        rng.shuffle(order)
        cur, peak, mdd, consec, worst_streak = equity, equity, 0.0, 0, 0
        for pnl in order:
            cur += pnl
            peak = max(peak, cur)
            mdd = max(mdd, (peak - cur) / peak * 100 if peak else 0)
            consec = consec + 1 if pnl <= 0 else 0
            worst_streak = max(worst_streak, consec)
        dds.append(mdd)
        streaks.append(worst_streak)
        if mdd > 10.0 or worst_streak >= 8:
            bad += 1
    dds.sort()
    out = {"sims": sims, "p_bad_path": round(bad / sims, 3),
           "p95_max_dd_pct": round(dds[int(0.95 * sims)], 2),
           "median_max_dd_pct": round(dds[sims // 2], 2),
           "p95_max_consec_losses": sorted(streaks)[int(0.95 * sims)],
           "verdict": "ROBUST" if bad / sims < 0.2 else "FRAGILE"}
    return out


def sensitivity(candles: list[Candle], equity: float = 10000.0, risk_pct: float = 1.0,
                warmup: int = 200, grid: dict | None = None) -> dict:
    grid = grid or PARAM_GRID
    rows = []
    prep = prepare_bars(candles, warmup)
    for sl in grid["sl_mult"]:
        for tp in grid["tp_mult"]:
            for mc in grid["min_conf"]:
                r = run_backtest(candles, equity, risk_pct, warmup, 10, 0.3, sl, tp, mc, prep=prep)
                rows.append({"sl_mult": sl, "tp_mult": tp, "min_conf": mc,
                             "trades": r["trades"], "pf": round(_pf_of(r), 2), "net": r["net_pnl"]})
    good = [x for x in rows if x["pf"] >= 1.2 and x["trades"] >= 5]
    stability = round(len(good) / len(rows), 2)
    return {"grid": rows, "stable_fraction_pf_ge_1_2": stability,
            "verdict": "STABLE" if stability >= 0.5 else "CLIFF_RISK",
            "note": ">=50% of param combos profitable = plateau, not a tuned spike"}


def benchmark_gate(candles: list[Candle], net_pnl: float, equity: float = 10000.0) -> dict:
    if len(candles) < 2:
        return {"bh_pnl": 0.0, "required": 0.0, "passed": False, "reason": "no data"}
    # Buy-and-hold notional on same equity over the same window.
    bh_ret = (candles[-1].close - candles[0].close) / candles[0].close
    bh_pnl = round(bh_ret * equity, 2)
    if bh_pnl <= 0:
        passed = net_pnl > 0
        reason = f"B&H {bh_pnl}: strategy must simply be net-positive (net {net_pnl})"
    else:
        required = round(0.3 * bh_pnl, 2)
        passed = net_pnl >= required
        reason = f"B&H {bh_pnl}: strategy net {net_pnl} vs 30% bar {required}"
    return {"bh_pnl": bh_pnl, "required": required if bh_pnl > 0 else 0.0,
            "passed": passed, "reason": reason}


def full_audit(candles: list[Candle], equity: float = 10000.0, risk_pct: float = 1.0,
               warmup: int = 200, folds: int = 3, grid: dict | None = None) -> dict:
    base = run_backtest(candles, equity, risk_pct, warmup, return_all_trades=True,
                             prep=prepare_bars(candles, warmup))
    wf = walk_forward(candles, folds, equity, risk_pct, warmup, grid)
    mc = monte_carlo([t["pnl"] for t in base.get("trades_full", [])])
    sens = sensitivity(candles, equity, risk_pct, warmup, grid)
    bench = benchmark_gate(candles, base["net_pnl"], equity)
    reasons = []
    if wf["verdict"] != "ROBUST":
        reasons.append(f"walk-forward {wf['verdict']} (eff {wf['avg_wf_efficiency']})")
    if mc.get("verdict") != "ROBUST":
        reasons.append(f"monte-carlo {mc.get('verdict')} (P(bad-path)={mc.get('p_bad_path')})")
    if sens["verdict"] != "STABLE":
        reasons.append(f"sensitivity {sens['verdict']} ({sens['stable_fraction_pf_ge_1_2']})")
    if not bench["passed"]:
        reasons.append(f"benchmark FAIL: {bench['reason']}")
    if base["gate"] == "REJECT":
        reasons.append(f"base gate REJECT: {base['gate_reasons']}")
    # Final can never exceed the base gate (e.g. base WAIT on <50 trades caps at WAIT).
    cap = {"PROMOTE": 2, "WAIT": 1, "REJECT": 0}
    level = cap.get(base["gate"], 1)
    if reasons:
        level = min(level, 1)
    if base["gate"] == "REJECT" or wf["verdict"] in ("WEAK", "NO_DATA"):
        level = 0
    gate = {2: "PROMOTE", 1: "WAIT", 0: "REJECT"}[level]
    return {"base": {k: base[k] for k in ("trades", "win_rate", "profit_factor", "net_pnl",
                                         "max_drawdown_pct", "gate")},
            "walk_forward": wf, "monte_carlo": mc, "sensitivity": sens,
            "benchmark": bench, "final_gate": gate, "final_reasons": reasons}
