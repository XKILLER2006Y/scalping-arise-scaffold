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
    assert j["meta"]["source"] in ("tradingview", "twelve_data", "yfinance")
    assert j["candles"][0]["source_type"] == "SPOT"

def test_market_analysis_no_signals():
    c = client.get("/api/v1/market-data/candles", params={"limit": 80}).json()["candles"]
    r = client.post("/api/v1/market-analysis", json={"symbol": "XAU/USD", "candles": c})
    assert r.status_code == 200
    j = r.json()
    assert "trend" in j and "regime" in j
    assert "BUY" not in str(j) and "SELL" not in str(j)

def test_technical_core_with_extension():
    c = client.get("/api/v1/market-data/candles", params={"limit": 100}).json()["candles"]
    r = client.post("/api/v1/technical-features", json={"symbol": "XAU/USD", "candles": c})
    assert r.status_code == 200
    j = r.json()
    assert j["features"]["ema20"] is not None and j["features"]["rsi14"] is not None
    assert j["volatility"] in ("LOW_VOLATILITY", "NORMAL_VOLATILITY", "HIGH_VOLATILITY", "EXTREME_VOLATILITY", None)
    assert j["status"] in ("READY", "WARMING_UP", "UNAVAILABLE")
    assert "BUY" not in str(j)

def test_futures_proxy_never_equals_spot():
    from app.market_data.providers.base import YFinanceProvider
    cs = YFinanceProvider().fetch_candles("XAU/USD", "1m", 5)
    assert all(x.source_type == "FUTURES_PROXY" for x in cs)
    assert all(x.provider_instrument == "GC=F" for x in cs)

def test_tradingview_primary_with_failover(monkeypatch):
    from app.market_data import service as svc
    from app.market_data.providers.base import synth_candles
    from app.market_data.models import SourceType
    import app.market_data.service as svcmod
    # TV works -> primary
    monkeypatch.setattr("app.market_data.providers.tradingview_provider.TradingViewProvider.fetch_candles",
                        lambda self, s="XAU/USD", tf="1m", limit=100: synth_candles("tradingview", "OANDA:XAUUSD", SourceType.SPOT, n=limit))
    svc._cache.clear()
    _, meta = svc.get_candles("XAU/USD", "1m", 5)
    assert meta["source"] == "tradingview" and meta["source_type"] == "SPOT"
    # TV down -> Twelve/yfinance failover still serves
    def boom(self, s="XAU/USD", tf="1m", limit=100):
        raise RuntimeError("tv down")
    monkeypatch.setattr("app.market_data.providers.tradingview_provider.TradingViewProvider.fetch_candles", boom)
    svc._cache.clear()
    _, meta2 = svc.get_candles("XAU/USD", "1m", 5)
    assert meta2["source"] in ("twelve_data", "yfinance")
    svc._cache.clear()
