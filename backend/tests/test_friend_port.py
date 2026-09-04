"""Ported-concept tests (ideas + adapted code w/ permission from Hash-sudo-cell/scalping-arise).

Covers: PULLBACK_CONT strategy, invalidation vetoes, eligibility gate,
LRU eviction, GET quick endpoints.
"""
from fastapi.testclient import TestClient
from app.main import app
from app.market_data.providers.base import synth_candles
from app.market_data.models import SourceType
from app.strategy.invalidation import evaluate_invalidation
from app.strategy.eligibility import check_eligibility

client = TestClient(app)

def _cs(n=260):
    return [c.model_dump() for c in synth_candles("twelve_data", "XAU/USD", SourceType.SPOT, n=n)]

def test_three_strategies_evaluated():
    a = client.post("/api/v1/market-analysis", json={"symbol": "XAU/USD", "candles": _cs(220)}).json()
    f = client.post("/api/v1/technical-features", params={"timeframe": "1m"},
                    json={"symbol": "XAU/USD", "candles": _cs(220)}).json()
    feats = dict(f["features"]); feats["volatility"] = f["volatility"]
    r = client.post("/api/v1/strategy/evaluate", json={"analysis": a, "features": feats, "close": 2650.0})
    evs = {e["strategy"]: e for e in r.json()["evaluations"]}
    assert set(evs) == {"TREND_CONT", "PULLBACK_CONT", "RANGE_FADE"}
    for e in evs.values():
        assert "eligibility" in e and "invalidation" in e

def test_invalidation_vetoes():
    base = {"trend": "UPTREND", "regime": "TRENDING", "bos": False, "choch": False,
            "support": [2640.0], "resistance": [2660.0], "sweeps": [], "fvgs": []}
    feats = {"atr14": 2.0}
    # CHOCH veto
    r = evaluate_invalidation("TREND_CONT", {**base, "choch": True}, "LONG", feats, [2650.0] * 30)
    assert any(x["triggered"] and x["rule_id"] == "tc_inval_choch" for x in r)
    # regime veto
    r = evaluate_invalidation("TREND_CONT", {**base, "trend": "RANGE"}, "LONG", feats, [2650.0] * 30)
    assert any(x["triggered"] and x["rule_id"] == "tc_inval_regime_shift" for x in r)
    # breakout veto on fade
    r = evaluate_invalidation("RANGE_FADE", {**base, "trend": "RANGE", "bos": True}, "LONG", feats, [2650.0] * 30)
    assert any(x["triggered"] and x["rule_id"] == "rr_inval_breakout" for x in r)
    # opposing sweep veto
    sw = {**base, "sweeps": [{"type": "SSL_SWEEP", "i": 5, "level": 2649.0}]}
    r = evaluate_invalidation("TREND_CONT", sw, "LONG", feats, [2650.0] * 30)
    assert any(x["triggered"] and "sweep" in x["rule_id"] for x in r)
    # deep pullback veto: steady grind down = full retrace
    closes = [2660.0 - i * 0.5 for i in range(30)]
    r = evaluate_invalidation("PULLBACK_CONT", base, "LONG", feats, closes)
    assert any(x["triggered"] and x["rule_id"] == "pc_inval_deep_pullback" for x in r)
    # clean setup: nothing triggered
    r = evaluate_invalidation("TREND_CONT", base, "LONG", feats, [2650.0 + (i % 3) * 0.1 for i in range(30)])
    assert not any(x["triggered"] for x in r)

def test_eligibility_blocks():
    a = {"trend": "UPTREND"}
    f = {"ema20": 1.0, "rsi14": 55.0, "atr14": 2.0}
    ok = check_eligibility("TREND_CONT", a, f, 250, "SPOT")
    assert ok["eligible"] and ok["blocked_by"] is None
    bad = check_eligibility("TREND_CONT", a, f, 10, "SPOT")
    assert not bad["eligible"] and bad["blocked_by"] == "candles_sufficient"
    bad2 = check_eligibility("RANGE_FADE", {"trend": "UPTREND"}, f, 250, "SPOT")
    assert not bad2["eligible"] and bad2["blocked_by"] == "regime_compatible"
    bad3 = check_eligibility("TREND_CONT", {}, f, 250, "SPOT")
    assert not bad3["eligible"]

def test_lru_eviction():
    # Direct unit test (no HTTP): 40 puts must evict down to max 32 entries.
    from app.market_data import service as md_service
    from app.market_data.providers.base import synth_candles
    for i in range(40):
        md_service._cache_put(f"T{i}|1m", (0.0, synth_candles("twelve_data", "XAU/USD", SourceType.SPOT, n=5)))
    s = md_service.cache_stats()
    assert s["entries"] <= s["max_entries"] == 32
    # newest keys survive, oldest evicted
    assert "T39|1m" in s["keys"] and "T0|1m" not in s["keys"]

def test_get_quick_endpoints():
    r = client.get("/api/v1/strategy/evaluate-quick", params={"symbol": "XAU/USD", "timeframe": "1m", "limit": 250})
    assert r.status_code == 200
    assert len(r.json()["evaluations"]) == 3
    t = client.get("/api/v1/system/trace-quick", params={"symbol": "XAU/USD", "limit": 250})
    assert t.status_code == 200
    assert "signal" in t.json() and "exposure" in t.json()
