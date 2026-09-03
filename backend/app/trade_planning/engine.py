"""Phase 7: entry/SL/TP/RR/sizing/spread+cost gate, multi-TP. Plan only."""
def plan(signal: dict, entry: float, atr: float | None, equity: float = 10000.0,
         risk_pct: float = 1.0, spread: float = 0.3, contract_oz: float = 100.0,
         extra_cost: float = 0.2) -> dict:
    if signal.get("action") == "NO_TRADE" or atr is None or atr <= 0:
        return {"feasible": False, "reason": "no trade or ATR unavailable", "signal": signal}
    direction = signal.get("direction")
    sl_dist = 1.5 * atr
    tp_dist = 2.0 * sl_dist
    sl = entry - sl_dist if direction == "LONG" else entry + sl_dist
    tp = entry + tp_dist if direction == "LONG" else entry - tp_dist
    rr = tp_dist / sl_dist if sl_dist else 0
    risk_money = equity * risk_pct / 100.0
    lots_raw = risk_money / (sl_dist * contract_oz) if sl_dist else 0
    lots = max(0.0, round(lots_raw - 0.005, 2))
    cost = spread + extra_cost
    spread_ok = spread <= 0.5 * atr
    # cost gate (cf. gold-pro-scalper): TP must be >= 4x round-trip cost, ATR >= 3x cost
    cost_ok = (tp_dist >= 4 * cost) and (atr >= 3 * cost)
    rr_ok = rr >= 1.5
    feasible = spread_ok and cost_ok and rr_ok and lots >= 0.01
    reasons = []
    if not spread_ok:
        reasons.append(f"spread {spread} > 0.5*ATR {0.5*atr:.2f}")
    if not cost_ok:
        reasons.append(f"cost gate fail: need TP {tp_dist:.2f}>=4xcost {4*cost:.2f} and ATR {atr:.2f}>=3xcost {3*cost:.2f}")
    if not rr_ok:
        reasons.append(f"RR {rr:.2f} < 1.5")
    if lots < 0.01:
        reasons.append(f"lots {lots} below 0.01 minimum — stop too wide for account")
    # multi-TP ladder (partial-close plan, cf. nixie-gold-bot)
    multis = []
    if feasible or True:
        for name, rmult, pct in (("TP1", 1.5, 45), ("TP2", 2.5, 30), ("TP3", 4.0, 25)):
            d = rmult * sl_dist
            px = entry + d if direction == "LONG" else entry - d
            multis.append({"name": name, "price": round(px, 2), "r": rmult, "close_pct": pct})
    return {"feasible": feasible, "entry": entry, "stop": round(sl, 2), "take_profit": round(tp, 2),
            "sl_distance": round(sl_dist, 2), "tp_distance": round(tp_dist, 2), "rr": round(rr, 2),
            "risk_money": round(risk_money, 2), "lots": lots, "spread": spread, "cost": round(cost, 2),
            "spread_ok": spread_ok, "cost_ok": cost_ok, "multi_tp": multis,
            "breakeven_note": "move SL to breakeven after TP1 (if executed)",
            "reasons": reasons, "order_type": "MARKET",
            "note": "Plan only. No execution."}
