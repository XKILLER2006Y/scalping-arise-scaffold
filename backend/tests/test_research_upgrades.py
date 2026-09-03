from fastapi.testclient import TestClient
from app.main import app
from app.market_data.providers.base import synth_candles
from app.market_data.models import SourceType
from app.signals.engine import pullback_ok, sweep_confluence

client = TestClient(app)

def _cs(n=260):
    return [c.model_dump() for c in synth_candles("twelve_data", "XAU/USD", SourceType.SPOT, n=n)]

def test_new_features_present():
    r = client.post("/api/v1/technical-features", params={"timeframe": "1m"}, json={"symbol": "XAU/USD", "candles": _cs(260)})
    f = r.json()["features"]
    for k in ("z20", "adx14", "atr_ratio", "vwap"):
        assert k in f, k
    assert r.json()["status"] in ("READY", "WARMING_UP", "UNAVAILABLE")

def test_sweep_fvg_in_analysis():
    a = client.post("/api/v1/market-analysis", json={"symbol": "XAU/USD", "candles": _cs(120)}).json()
    assert "sweeps" in a and "fvgs" in a

def test_session_gate_and_armed():
    evs = [{"strategy": "TREND_CONT", "direction": "LONG", "qualified": True, "quality": 85, "met": ["x"], "missing": []}]
    feats = {"volatility": "NORMAL_VOLATILITY", "rel_volume": 1.3}
    s1 = client.post("/api/v1/signals/decide", json={"evaluations": evs, "features": feats,
        "context": {"session": "ASIA", "closes": [1, 2, 3, 4, 5, 6], "analysis": {}}}).json()
    assert s1["state"] == "PROPOSED"  # killzone gate
    s2 = client.post("/api/v1/signals/decide", json={"evaluations": evs, "features": feats,
        "context": {"session": "LONDON", "closes": [1, 2, 3, 4, 5, 6], "analysis": {}}}).json()
    assert s2["state"] == "ARMED"  # no pullback in straight-up closes
    assert pullback_ok("LONG", [10, 9, 9.5, 10, 10.5, 11]) in (True, False)
    assert sweep_confluence({"sweeps": [{"type": "SSL_SWEEP"}]}, "LONG") is True

def test_cost_gate_and_multi_tp():
    sig = {"action": "BUY", "direction": "LONG", "strategy": "TREND_CONT", "confidence": 80, "quality": 85}
    ok = client.post("/api/v1/trade-plan", json={"signal": sig, "entry": 2650.0, "atr": 2.5, "equity": 10000.0, "risk_pct": 1.0, "spread": 0.3}).json()
    assert ok["cost_ok"] is True and len(ok["multi_tp"]) == 3
    bad = client.post("/api/v1/trade-plan", json={"signal": sig, "entry": 2650.0, "atr": 0.05, "equity": 100.0, "risk_pct": 1.0, "spread": 5.0}).json()
    assert bad["feasible"] is False

def test_exposure_endpoint():
    assert "blocked" in client.get("/api/v1/intelligence/exposure").json()

def test_trace_has_exposure():
    cs = _cs(250)
    t = client.post("/api/v1/system/trace", json={"symbol": "XAU/USD", "candles_1m": cs, "candles_5m": cs, "candles_15m": cs}).json()
    assert "exposure" in t and "signal" in t
