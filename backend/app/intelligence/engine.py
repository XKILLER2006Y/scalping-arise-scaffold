"""Phase 8: news blocklist + performance controller + daily exposure guards. Protective only."""
import time
import datetime

BLOCKED_WINDOWS: list[tuple[int, int]] = []
_stats: dict[str, dict] = {}
_day: dict[str, dict] = {"date": "", "trades": 0, "pnl": 0.0, "consec_losses": 0, "last_loss_t": 0}
MAX_TRADES_PER_DAY = 10
MAX_DAILY_LOSS_PCT = 5.0
COOLDOWN_AFTER_CONSEC_LOSSES = 2
COOLDOWN_SECONDS = 30 * 60

def _today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

def is_blocked(now: int | None = None) -> dict:
    t = now if now is not None else int(time.time())
    for a, b in BLOCKED_WINDOWS:
        if a <= t <= b:
            return {"blocked": True, "reason": f"inside high-impact window {a}-{b}"}
    return {"blocked": False, "reason": None}

def exposure_guard(equity: float = 10000.0, now: int | None = None) -> dict:
    t = now if now is not None else int(time.time())
    if _day["date"] != _today():
        _day.update({"date": _today(), "trades": 0, "pnl": 0.0, "consec_losses": 0, "last_loss_t": 0})
    if _day["trades"] >= MAX_TRADES_PER_DAY:
        return {"blocked": True, "reason": f"max {MAX_TRADES_PER_DAY} trades/day reached"}
    if equity > 0 and (-_day["pnl"] / equity * 100) >= MAX_DAILY_LOSS_PCT:
        return {"blocked": True, "reason": f"daily loss limit -{MAX_DAILY_LOSS_PCT}% hit"}
    if _day["consec_losses"] >= COOLDOWN_AFTER_CONSEC_LOSSES and (t - _day["last_loss_t"]) < COOLDOWN_SECONDS:
        left = int((COOLDOWN_SECONDS - (t - _day["last_loss_t"])) / 60)
        return {"blocked": True, "reason": f"loss cooldown: {left}m left after {_day['consec_losses']} consecutive losses"}
    return {"blocked": False, "reason": None}

def record(strategy: str, pnl: float):
    s = _stats.setdefault(strategy, {"wins": 0, "losses": 0, "gross_win": 0.0, "gross_loss": 0.0})
    if _day["date"] != _today():
        _day.update({"date": _today(), "trades": 0, "pnl": 0.0, "consec_losses": 0, "last_loss_t": 0})
    _day["trades"] += 1
    _day["pnl"] += pnl
    if pnl >= 0:
        s["wins"] += 1; s["gross_win"] += pnl; _day["consec_losses"] = 0
    else:
        s["losses"] += 1; s["gross_loss"] += -pnl
        _day["consec_losses"] += 1; _day["last_loss_t"] = int(time.time())

def status(strategy: str) -> dict:
    s = _stats.get(strategy, {"wins": 0, "losses": 0, "gross_win": 0.0, "gross_loss": 0.0})
    n = s["wins"] + s["losses"]
    pf = (s["gross_win"] / s["gross_loss"]) if s["gross_loss"] else (float("inf") if s["gross_win"] else 0.0)
    wr = s["wins"] / n if n else 0.0
    disabled = (n >= 20 and (pf < 1.0 or wr < 0.30))
    return {"strategy": strategy, "trades": n, "profit_factor": round(pf, 2) if pf != float("inf") else None,
            "win_rate": round(wr, 3), "disabled": disabled,
            "day": dict(_day),
            "reason": "PF<1.0 or WR<30% after 20 trades" if disabled else None}
