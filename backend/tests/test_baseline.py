from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_market_data_flow_preserves_source():
    r = client.get("/api/v1/market-data/candles", params={"symbol": "XAU/USD", "timeframe": "1m", "limit": 50})
    assert r.status_code == 200
    j = r.json()
    assert j["meta"]["source_type"] == "SPOT"
    assert j["candles"][0]["provider_instrument"] == "XAU/USD"
    assert j["candles"][0]["source_type"] == "SPOT"

def test_market_analysis_no_signals():
    c = client.get("/api/v1/market-data/candles", params={"limit": 80}).json()["candles"]
    r = client.post("/api/v1/market-analysis", json={"symbol": "XAU/USD", "candles": c})
    assert r.status_code == 200
    j = r.json()
    assert "trend" in j and "regime" in j
    assert "BUY" not in str(j) and "SELL" not in str(j)

def test_technical_core_no_extension():
    c = client.get("/api/v1/market-data/candles", params={"limit": 100}).json()["candles"]
    r = client.post("/api/v1/technical-features", json={"symbol": "XAU/USD", "candles": c})
    assert r.status_code == 200
    j = r.json()
    assert j["ema20"] is not None and j["rsi14"] is not None
    assert "volatility" not in j  # extension NOT implemented
    assert "BUY" not in str(j)

def test_futures_proxy_never_equals_spot():
    from app.market_data.providers.base import YFinanceProvider
    cs = YFinanceProvider().fetch_candles("XAU/USD", "1m", 5)
    assert all(x.source_type == "FUTURES_PROXY" for x in cs)
    assert all(x.provider_instrument == "GC=F" for x in cs)
