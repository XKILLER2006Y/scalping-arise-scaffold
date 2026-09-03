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
