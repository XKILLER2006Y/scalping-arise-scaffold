import math

def create_plan(signal: dict, entry: float, atr: float | None, equity: float = 10000.0,
         risk_pct: float = 1.0, spread: float = 0.3, contract_oz: float = 100.0,
         extra_cost: float = 0.2, ml_confidence: float = 50.0) -> dict:
    if (
        signal.get("action") == "NO_TRADE"
        or atr is None
        or entry is None
        or math.isnan(entry)
        or math.isinf(entry)
        or math.isnan(atr)
        or math.isinf(atr)
        or atr <= 0
        or entry <= 0
    ):
        safe_entry = entry if (entry is not None and not math.isnan(entry) and not math.isinf(entry)) else 0.0
        return {
            "action": "NO_TRADE",
            "direction": None,
            "feasible": False,
            "reason": "no trade or ATR unavailable",
            "signal": signal,
            "entry": safe_entry,
            "entry_price": safe_entry,
            "stop": None,
            "stop_loss": None,
            "take_profit": None,
            "take_profit_1": None,
            "lots": 0.0,
            "position_size": 0.0,
        }
    direction = signal.get("direction")
    sl_dist = 1.5 * atr
    tp_dist = 2.0 * sl_dist
    sl = entry - sl_dist if direction == "LONG" else entry + sl_dist
    tp = entry + tp_dist if direction == "LONG" else entry - tp_dist
    rr = tp_dist / sl_dist if sl_dist else 0
    
    # Sanitize and clamp ml_confidence to [0.0, 100.0]
    try:
        if ml_confidence is None:
            clean_ml_conf = 50.0
        else:
            f_conf = float(ml_confidence)
            if math.isnan(f_conf) or math.isinf(f_conf):
                clean_ml_conf = 50.0
            else:
                clean_ml_conf = max(0.0, min(100.0, f_conf))
    except (ValueError, TypeError):
        clean_ml_conf = 50.0

    # Kelly Criterion for position sizing based on ML confidence
    p = (clean_ml_conf / 100.0)
    q = 1.0 - p
    b = rr
    if b > 0 and p > 0.5:
        f_star = (p * b - q) / b
        kelly_fraction = max(0.0, min(f_star * 0.5, 0.02)) # Half-Kelly, capped at 2% risk
    else:
        kelly_fraction = (risk_pct / 100.0) if risk_pct else 0.01 # Fallback to static risk
    
    risk_money = equity * kelly_fraction
    lots_raw = risk_money / (sl_dist * contract_oz) if sl_dist else 0
    if math.isnan(lots_raw) or math.isinf(lots_raw) or lots_raw < 0:
        lots = 0.0
    else:
        lots = max(0.0, round(lots_raw - 0.005, 2))
    cost = spread + extra_cost
    spread_ok = spread <= 0.5 * atr
    # cost gate (cf. gold-pro-scalper): TP must be >= 4x round-trip cost, ATR >= 3x cost
    cost_ok = (tp_dist >= 4 * cost) and (atr >= 3 * cost)
    rr_ok = rr >= 1.5
    feasible = spread_ok and cost_ok and rr_ok and lots >= 0.01
    action = signal.get("action", "NO_TRADE") if feasible else "NO_TRADE"
    direction_val = signal.get("direction") if feasible else None
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
    return {
        "action": action,
        "direction": direction_val,
        "feasible": feasible,
        "entry": entry,
        "entry_price": entry,
        "stop": round(sl, 2),
        "stop_loss": round(sl, 2),
        "take_profit": round(tp, 2),
        "take_profit_1": round(tp, 2),
        "sl_distance": round(sl_dist, 2),
        "tp_distance": round(tp_dist, 2),
        "rr": round(rr, 2),
        "risk_money": round(risk_money, 2),
        "lots": lots,
        "position_size": lots,
        "spread": spread,
        "cost": round(cost, 2),
        "spread_ok": spread_ok,
        "cost_ok": cost_ok,
        "multi_tp": multis,
        "breakeven_note": "move SL to breakeven after TP1 (if executed)",
        "reasons": reasons,
        "order_type": "MARKET",
        "note": "Plan only. No execution.",
        "signal": signal,
    }


plan = create_plan
