"""Paper-forward truth loop: signals logged live, settled against future prices.

Backtests simulate fills; this watches what the bot ACTUALLY said and what the
market did next. Divergence between backtest expectancy and forward outcomes
is execution decay made visible — the research-demanded check.
Settlement is conservative: if a bar touches both SL and TP, SL wins (wicks
fill stops first in real books).
"""
from __future__ import annotations


def settle_one(open_sig: dict, bars: list[dict], max_bars: int = 60) -> dict | None:
    """bars: [{high, low, close}...] AFTER the signal bar. Returns settlement or None."""
    direction = open_sig.get("direction")
    sl, tp = open_sig.get("stop"), open_sig.get("tp")
    entry = open_sig.get("entry")
    if direction not in ("LONG", "SHORT") or not sl or not tp or not entry:
        return None
    for b in bars[:max_bars]:
        h, l = b.get("high"), b.get("low")
        if h is None or l is None:
            continue
        if direction == "LONG":
            if l <= sl:
                return _done(open_sig, "LOSS", sl, entry, sl)
            if h >= tp:
                return _done(open_sig, "WIN", tp, entry, sl)
        else:
            if h >= sl:
                return _done(open_sig, "LOSS", sl, entry, sl)
            if l <= tp:
                return _done(open_sig, "WIN", tp, entry, sl)
    last = bars[max_bars - 1] if len(bars) >= max_bars else (bars[-1] if bars else None)
    if last is None or last.get("close") is None:
        return None
    c = last["close"]
    # Timed out: exit at market, marked TIME (not WIN/LOSS — no level proved itself).
    gross = (c - entry) if direction == "LONG" else (entry - c)
    risk = abs(entry - sl) or 1e-9
    return {"id": open_sig["id"], "outcome": "TIME", "exit_px": round(c, 2),
            "r_mult": round(gross / risk, 2)}


def _done(open_sig: dict, outcome: str, exit_px: float, entry: float, sl: float,
          timed_out: bool = False) -> dict:
    risk = abs(entry - sl) or 1e-9
    gross = (exit_px - entry) if open_sig.get("direction") == "LONG" else (entry - exit_px)
    return {"id": open_sig["id"], "outcome": "TIME" if timed_out and outcome == "LOSS" and gross == 0 else outcome,
            "exit_px": round(exit_px, 2), "r_mult": round(gross / risk, 2)}


def divergence(backtest_expectancy_r: float, forward_avg_r: float, n_forward: int,
               min_n: int = 20) -> dict:
    """Execution decay = forward reality minus backtest promise."""
    if n_forward < min_n:
        return {"status": "WARMING_UP",
                "reason": f"only {n_forward} settled forward signals (need {min_n})"}
    gap = round(forward_avg_r - backtest_expectancy_r, 2)
    if gap >= -0.2:
        return {"status": "ALIGNED", "gap_r": gap, "reason": "forward tracks backtest"}
    if gap >= -0.8:
        return {"status": "DECAYING", "gap_r": gap,
                "reason": "forward underperforms: slippage/costs/regime suspected"}
    return {"status": "DIVERGED", "gap_r": gap,
            "reason": "forward decisively worse — halt sizing, investigate"}
