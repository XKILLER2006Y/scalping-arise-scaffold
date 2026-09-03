"""Phase 8: news blocklist + performance controller. Protective only."""
import time

# Configurable high-impact blackout windows (epoch seconds). Empty by default in scaffold.
BLOCKED_WINDOWS: list[tuple[int, int]] = []
_stats: dict[str, dict] = {}

def is_blocked(now: int | None = None) -> dict:
    t = now if now is not None else int(time.time())
    for a, b in BLOCKED_WINDOWS:
        if a <= t <= b:
            return {"blocked": True, "reason": f"inside high-impact window {a}-{b}"}
    return {"blocked": False, "reason": None}

def record(strategy: str, pnl: float):
    s = _stats.setdefault(strategy, {"wins": 0, "losses": 0, "gross_win": 0.0, "gross_loss": 0.0})
    if pnl >= 0:
        s["wins"] += 1; s["gross_win"] += pnl
    else:
        s["losses"] += 1; s["gross_loss"] += -pnl

def status(strategy: str) -> dict:
    s = _stats.get(strategy, {"wins": 0, "losses": 0, "gross_win": 0.0, "gross_loss": 0.0})
    n = s["wins"] + s["losses"]
    pf = (s["gross_win"] / s["gross_loss"]) if s["gross_loss"] else (float("inf") if s["gross_win"] else 0.0)
    wr = s["wins"] / n if n else 0.0
    disabled = (n >= 20 and (pf < 1.0 or wr < 0.30))
    return {"strategy": strategy, "trades": n, "profit_factor": round(pf, 2) if pf != float("inf") else None,
            "win_rate": round(wr, 3), "disabled": disabled,
            "reason": "PF<1.0 or WR<30% after 20 trades" if disabled else None}
