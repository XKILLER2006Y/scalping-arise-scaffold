"""Enterprise guards, stdlib-only: optional API key + in-memory rate limit."""
import time
import threading
from fastapi import Request
from fastapi.responses import JSONResponse
from app.core.config import settings

_hits: dict[str, list[float]] = {}
_hits_lock = threading.Lock()
RATE_PER_MIN = 120
_MAX_TRACKED_IPS = 5000  # leak cap: internet-facing dict must not grow forever

def _client_ip(req: Request) -> str:
    fwd = req.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return req.client.host if req.client else "unknown"

async def guard(request: Request, call_next):
    # 1) optional API key (free, no vendor)
    need = getattr(settings, "sca_api_key", "") or ""
    if need:
        got = request.headers.get("x-api-key", "")
        if got != need:
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
    # 2) rate limit (skip health/metrics)
    if request.url.path not in ("/api/v1/health", "/api/v1/system/health", "/api/v1/system/metrics"):
        now = time.time()
        ip = _client_ip(request)
        with _hits_lock:
            wins = [t for t in _hits.get(ip, []) if now - t < 60]
            if len(wins) >= RATE_PER_MIN:
                return JSONResponse(status_code=429, content={"error": "rate_limited", "retry_after_s": 60})
            wins.append(now)
            _hits[ip] = wins[-RATE_PER_MIN:]
            # Evict stale IPs so the tracker can't grow unbounded (spoofed
            # X-Forwarded-For = unlimited distinct keys without this).
            if len(_hits) > _MAX_TRACKED_IPS:
                cutoff = now - 60
                for k in [k for k, v in _hits.items() if not v or v[-1] < cutoff]:
                    del _hits[k]
                while len(_hits) > _MAX_TRACKED_IPS:
                    _hits.pop(next(iter(_hits)))
    return await call_next(request)
