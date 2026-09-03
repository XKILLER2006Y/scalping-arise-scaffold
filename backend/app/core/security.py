"""Enterprise guards, stdlib-only: optional API key + in-memory rate limit."""
import time
from fastapi import Request
from fastapi.responses import JSONResponse
from app.core.config import settings

_hits: dict[str, list[float]] = {}
RATE_PER_MIN = 120

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
        wins = [t for t in _hits.get(ip, []) if now - t < 60]
        if len(wins) >= RATE_PER_MIN:
            return JSONResponse(status_code=429, content={"error": "rate_limited", "retry_after_s": 60})
        wins.append(now)
        _hits[ip] = wins[-RATE_PER_MIN:]
    return await call_next(request)
