from fastapi.testclient import TestClient
from app.main import app
from app.market_data.providers.base import synth_candles
from app.market_data.models import SourceType

client = TestClient(app)

def _candles(n: int):
    return synth_candles("twelve_data", "XAU/USD", SourceType.SPOT, n=n)

def test_mtf_independent_no_decision():
    payload = {"symbol": "XAU/USD",
               "candles_by_timeframe": {"1m": [c.model_dump() for c in _candles(210)],
                                        "5m": [c.model_dump() for c in _candles(210)],
                                        "15m": [c.model_dump() for c in _candles(30)]}}
    r = client.post("/api/v1/technical-features/mtf", json=payload)
    assert r.status_code == 200
    j = r.json()
    assert set(j["timeframes"].keys()) == {"1m", "5m", "15m"}
    assert j["timeframes"]["1m"]["status"] == "READY"
    assert j["timeframes"]["15m"]["status"] == "WARMING_UP"
    for tf in ("1m", "5m", "15m"):
        assert "decision" not in j["timeframes"][tf]
        assert "action" not in j["timeframes"][tf]
        assert "order" not in j["timeframes"][tf]
    assert j["timeframes"]["1m"].get("decision", None) is None
    # source preserved per TF
    assert j["timeframes"]["1m"]["source_type"] == "SPOT"

def test_volatility_classes_boundaries():
    from app.technical_features.engine import classify_volatility
    from app.core.config import settings
    # low
    v, _ = classify_volatility(1.0, 2650.0)  # 0.00037
    assert v == "LOW_VOLATILITY"
    # force extreme
    v2, _ = classify_volatility(20.0, 2650.0)  # 0.0075
    assert v2 == "EXTREME_VOLATILITY"
    assert settings.vol_low_max < settings.vol_normal_max < settings.vol_high_max

def test_status_unavailable_and_reason():
    r = client.post("/api/v1/technical-features", params={"timeframe": "5m"},
                    json={"symbol": "XAU/USD", "candles": []})
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "UNAVAILABLE"
    assert j["reason"] is not None

def test_no_lookahead_single_tf():
    cs = _candles(210)
    r1 = client.post("/api/v1/technical-features", params={"timeframe": "1m"},
                     json={"symbol": "XAU/USD", "candles": [c.model_dump() for c in cs[:200]]})
    r2 = client.post("/api/v1/technical-features", params={"timeframe": "1m"},
                     json={"symbol": "XAU/USD", "candles": [c.model_dump() for c in cs[:201]]})
    # different input length -> features computed only from given closed candles
    assert r1.json()["candle_count"] == 200
    assert r2.json()["candle_count"] == 201
