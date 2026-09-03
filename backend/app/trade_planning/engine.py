"""Phase 7: entry/SL/TP/RR/sizing/spread check. No execution, planning only."""
def plan(signal: dict, entry: float, atr: float | None, equity: float = 10000.0,
         risk_pct: float = 1.0, spread: float = 0.3, contract_oz: float = 100.0) -> dict:
    if signal.get("action") == "NO_TRADE" or atr is None or atr <= 0:
        return {"feasible": False, "reason": "no trade or ATR unavailable", "signal": signal}
    direction = signal.get("direction")
    sl_dist = 1.5 * atr
    sl = entry - sl_dist if direction == "LONG" else entry + sl_dist
    tp_dist = 2.0 * sl_dist
    tp = entry + tp_dist if direction == "LONG" else entry - tp_dist
    rr = tp_dist / sl_dist if sl_dist else 0
    risk_money = equity * risk_pct / 100.0
    lots_raw = risk_money / (sl_dist * contract_oz) if sl_dist else 0
    lots = max(0.0, round(lots_raw - 0.005, 2))  # round down-ish
    spread_ok = spread <= 0.5 * atr
    rr_ok = rr >= 1.5
    feasible = spread_ok and rr_ok and lots >= 0.01
    reasons = []
    if not spread_ok:
        reasons.append(f"spread {spread} > 0.5*ATR {0.5*atr:.2f}")
    if not rr_ok:
        reasons.append(f"RR {rr:.2f} < 1.5")
    if lots < 0.01:
        reasons.append(f"lots {lots} below 0.01 minimum — stop too wide for account")
    return {"feasible": feasible, "entry": entry, "stop": round(sl, 2), "take_profit": round(tp, 2),
            "sl_distance": round(sl_dist, 2), "tp_distance": round(tp_dist, 2), "rr": round(rr, 2),
            "risk_money": round(risk_money, 2), "lots": lots, "spread": spread,
            "spread_ok": spread_ok, "reasons": reasons, "order_type": "MARKET",
            "note": "Plan only. No execution."}
