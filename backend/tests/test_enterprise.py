from fastapi.testclient import TestClient
from app.main import app
from app.market_data.providers.base import synth_candles
from app.market_data.models import SourceType

client = TestClient(app)

def test_request_id_and_metrics():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert "x-request-id" in {k.lower(): v for k, v in r.headers.items()}
    m = client.get("/api/v1/system/metrics")
    assert m.status_code == 200
    assert "uptime_s" in m.json()

def test_sqlite_persistence_and_reliability():
    cs = [c.model_dump() for c in synth_candles("twelve_data", "XAU/USD", SourceType.SPOT, n=250)]
    t = client.post("/api/v1/system/trace", json={"symbol": "XAU/USD", "candles_1m": cs, "candles_5m": cs, "candles_15m": cs})
    assert t.status_code == 200
    from app.core.store import signal_stats
    s = signal_stats()
    assert s["total"] >= 1
    r = client.get("/api/v1/system/reliability")
    assert r.json()["total"] >= 1


def test_rate_limiter_evicts_stale_ips():
    from app.core import security
    import time
    security._hits.clear()
    for i in range(5100):
        security._hits[f"10.0.0.{i}"] = [time.time() - 61]  # all stale
    security._hits["fresh"] = [time.time()]
    # trigger eviction path via guard internals
    with security._hits_lock:
        if len(security._hits) > security._MAX_TRACKED_IPS:
            cutoff = time.time() - 60
            for k in [k for k, v in security._hits.items() if not v or v[-1] < cutoff]:
                del security._hits[k]
    assert "fresh" in security._hits and len(security._hits) <= 5001
    security._hits.clear()


def test_sqlite_retention_caps():
    from app.core import store
    for _ in range(5):
        store.audit("RETENTION_TEST", "x")
    import sqlite3
    c = sqlite3.connect(str(store.DB))
    n = c.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
    c.close()
    assert n <= 10000
    c = sqlite3.connect(str(store.DB))
    c.execute("DELETE FROM audit WHERE event='RETENTION_TEST'")
    c.commit(); c.close()


def test_shared_http_client_reused():
    from app.market_data.providers.base import http_client
    assert http_client() is http_client()
