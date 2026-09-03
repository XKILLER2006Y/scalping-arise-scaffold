"""Request-ID + structured access log + latency header. Stdlib only."""
import time
import uuid
from fastapi import Request
from app.core.logging import get_logger

log = get_logger("http")

async def request_id_log(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    t0 = time.time()
    resp = await call_next(request)
    ms = round((time.time() - t0) * 1000, 1)
    resp.headers["X-Request-ID"] = rid
    resp.headers["X-Latency-ms"] = str(ms)
    log.info(f"rid={rid} {request.method} {request.url.path} -> {resp.status_code} {ms}ms")
    return resp
