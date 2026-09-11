"""Decision hardening (adapted w/ permission from Hash-sudo-cell/scalping-arise
app/modules/decision/{expiration,idempotency,readiness}.py, rewritten dict-based):

- Expiry: every signal carries expires_at (TTL = 5x entry TF). Consumers must
  re-check; a stale BUY is worse than NO_TRADE.
- Idempotency: identical consecutive signals (strategy+direction+entry bar)
  dedupe to one alert — no spam on every poll.
- Readiness: /signal refuses with 503-style body unless providers + features
  are actually READY (never signal on WARMING_UP data).
"""
from __future__ import annotations
import hashlib
import json
import threading
import time
from collections import OrderedDict

SIGNAL_TTL_S = 300  # 5x 1m entry TF

_lock = threading.Lock()
_seen: OrderedDict[str, float] = OrderedDict()
_SEEN_MAX = 500
_SEEN_TTL = 600


def stamp_expiry(signal: dict, ttl_s: int = SIGNAL_TTL_S, bar_ts: int | None = None) -> dict:
    now = int(time.time())
    signal = dict(signal)
    signal["issued_at"] = now
    signal["expires_at"] = now + ttl_s
    if bar_ts is not None:
        signal["entry_bar_ts"] = bar_ts
    return signal


def is_expired(signal: dict, now: int | None = None) -> bool:
    exp = signal.get("expires_at")
    if exp is None:
        return False
    return int(now if now is not None else time.time()) > int(exp)


def dedupe_key(signal: dict) -> str:
    payload = {"strategy": signal.get("strategy"), "direction": signal.get("direction"),
               "bar": signal.get("entry_bar_ts")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def is_duplicate(signal: dict) -> bool:
    """True if this exact setup already alerted within TTL (idempotent signals)."""
    if signal.get("action") == "NO_TRADE":
        return False
    key = dedupe_key(signal)
    now = time.time()
    with _lock:
        # prune
        for k, ts in list(_seen.items()):
            if now - ts > _SEEN_TTL:
                del _seen[k]
        if key in _seen:
            return True
        _seen[key] = now
        while len(_seen) > _SEEN_MAX:
            _seen.popitem(last=False)
        return False


def readiness(market_meta: dict, features_status: str | None) -> dict:
    """Gate behind /signal: refuse unless data + features are genuinely READY."""
    checks = []
    src = (market_meta or {}).get("source")
    checks.append({"check": "provider_up", "passed": bool(src),
                   "reason": f"source={src}" if src else "no market data"})
    checks.append({"check": "features_ready", "passed": features_status == "READY",
                   "reason": f"features={features_status}"})
    blocked = [c["check"] for c in checks if not c["passed"]]
    return {"ready": not blocked, "blocked_by": blocked or None, "checks": checks}
