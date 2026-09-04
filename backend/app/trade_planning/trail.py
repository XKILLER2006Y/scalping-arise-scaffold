"""Volatility-adaptive trailing exits (Chandelier-style + breakeven discipline).

Research rule: a trailing stop too tight kills good trades, too wide gives it
all back. Anchor distance to ATR so the leash breathes with volatility, ratchet
only in the trade's favor, and move to breakeven once TP1 prints.
"""
from __future__ import annotations


def chandelier_stop(direction: str, highs: list[float], lows: list[float],
                    atr: float, k: float = 2.5) -> float | None:
    """Highest-high minus k*ATR (LONG) or lowest-low plus k*ATR (SHORT)."""
    if not highs or not lows or not atr or atr <= 0:
        return None
    if direction == "LONG":
        return max(highs) - k * atr
    if direction == "SHORT":
        return min(lows) + k * atr
    return None


def update_trail(state: dict, bar_high: float, bar_low: float, atr: float,
                 k: float = 2.5, lookback: int = 22) -> dict:
    """Advance one bar. state: {direction, entry, stop, tp1, tp1_done, highs, lows}.
    Returns {stop, exit, exit_price, reason}. Stop never loosens."""
    direction = state.get("direction")
    highs = list(state.get("highs", [])) + [bar_high]
    lows = list(state.get("lows", [])) + [bar_low]
    highs, lows = highs[-lookback:], lows[-lookback:]
    state["highs"], state["lows"] = highs, lows
    entry = state.get("entry", 0.0)
    stop = state.get("stop")

    # TP1 partial -> breakeven discipline.
    tp1 = state.get("tp1")
    if not state.get("tp1_done") and tp1 is not None:
        hit_tp1 = (bar_high >= tp1) if direction == "LONG" else (bar_low <= tp1)
        if hit_tp1:
            state["tp1_done"] = True
            be = entry
            stop = be if stop is None else (max(stop, be) if direction == "LONG" else min(stop, be))

    trail = chandelier_stop(direction or "", highs, lows, atr, k)
    if trail is not None:
        stop = trail if stop is None else (max(stop, trail) if direction == "LONG" else min(stop, trail))
    state["stop"] = stop

    exited, px, reason = False, None, None
    if stop is not None:
        if direction == "LONG" and bar_low <= stop:
            exited, px, reason = True, stop, "TRAIL"
        elif direction == "SHORT" and bar_high >= stop:
            exited, px, reason = True, stop, "TRAIL"
    # Hard TP cap (TP3) still stands above the trail.
    tp_cap = state.get("tp_cap")
    if not exited and tp_cap is not None:
        if direction == "LONG" and bar_high >= tp_cap:
            exited, px, reason = True, tp_cap, "TP_CAP"
        elif direction == "SHORT" and bar_low <= tp_cap:
            exited, px, reason = True, tp_cap, "TP_CAP"
    return {"stop": stop, "exit": exited, "exit_price": px, "reason": reason, "state": state}


def new_trail_state(direction: str, entry: float, stop: float,
                    tp1: float | None = None, tp_cap: float | None = None) -> dict:
    return {"direction": direction, "entry": entry, "stop": stop, "tp1": tp1,
            "tp_cap": tp_cap, "tp1_done": False, "highs": [], "lows": []}
