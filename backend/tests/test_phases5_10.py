from fastapi.testclient import TestClient
from app.main import app
from app.market_data.providers.base import synth_candles
from app.market_data.models import SourceType

client = TestClient(app)

def _cs(n=250):
    return [c.model_dump() for c in synth_candles("twelve_data", "XAU/USD", SourceType.SPOT, n=n)]

def test_phase5_evaluate_shape():
    candles = _cs(220)
    a = client.post("/api/v1/market-analysis", json={"symbol": "XAU/USD", "candles": candles}).json()
    f = client.post("/api/v1/technical-features", params={"timeframe": "1m"},
                    json={"symbol": "XAU/USD", "candles": candles}).json()
    feats = dict(f["features"]); feats["volatility"] = f["volatility"]
    r = client.post("/api/v1/strategy/evaluate", json={"analysis": a, "features": feats, "close": 2650.0})
    assert r.status_code == 200
    evs = r.json()["evaluations"]
    assert {e["strategy"] for e in evs} == {"TREND_CONT", "PULLBACK_CONT", "RANGE_FADE"}
    assert all("qualified" in e and "quality" in e for e in evs)

def test_phase6_decide_no_trade_or_signal():
    candles = _cs(220)
    a = client.post("/api/v1/market-analysis", json={"symbol": "XAU/USD", "candles": candles}).json()
    f = client.post("/api/v1/technical-features", params={"timeframe": "1m"},
                    json={"symbol": "XAU/USD", "candles": candles}).json()
    feats = dict(f["features"]); feats["volatility"] = f["volatility"]
    evs = client.post("/api/v1/strategy/evaluate", json={"analysis": a, "features": feats, "close": 2650.0}).json()["evaluations"]
    s = client.post("/api/v1/signals/decide", json={"evaluations": evs, "features": feats}).json()
    assert s["action"] in ("BUY", "SELL", "NO_TRADE")
    assert "confidence" in s and "quality" in s and "state" in s

def test_phase7_plan_rr_and_sizing():
    sig = {"action": "BUY", "direction": "LONG", "strategy": "TREND_CONT", "confidence": 70, "quality": 80}
    r = client.post("/api/v1/trade-plan", json={"signal": sig, "entry": 2650.0, "atr": 2.5, "equity": 10000.0, "risk_pct": 1.0, "spread": 0.3})
    assert r.status_code == 200
    j = r.json()
    assert j["rr"] == 2.0 and j["lots"] > 0 and j["feasible"] is True

def test_phase8_news_and_perf():
    assert client.get("/api/v1/intelligence/news-check").json()["blocked"] is False
    r = client.post("/api/v1/intelligence/record", json={"strategy": "TREND_CONT", "pnl": 10.0})
    assert r.status_code == 200 and "profit_factor" in r.json()

def test_phase9_backtest_gate():
    r = client.post("/api/v1/backtest/run", json={"candles": _cs(300), "equity": 10000.0, "risk_pct": 1.0})
    assert r.status_code == 200
    j = r.json()
    assert j["gate"] in ("PROMOTE", "WAIT", "REJECT")
    assert "profit_factor" in j and "max_drawdown_pct" in j

def test_phase10_trace_explains():
    cs = _cs(250)
    r = client.post("/api/v1/system/trace", json={"symbol": "XAU/USD", "candles_1m": cs, "candles_5m": cs, "candles_15m": cs})
    assert r.status_code == 200
    j = r.json()
    for k in ("market", "features_mtf", "evaluations", "signal", "trade_plan", "latency_ms"):
        assert k in j
    assert client.get("/api/v1/system/health").json()["status"] == "ok"
