"""OANDA connector tests (fully mocked HTTP — no token, no network)."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.brokers import oanda as oamod
from app.market_data.providers.oanda_provider import OandaProvider

client = TestClient(app)

CANDLES = {"candles": [
    {"complete": True, "volume": 120, "time": "2026-09-04T12:00:00.000000000Z",
     "mid": {"o": "4469.1", "h": "4470.2", "l": "4468.5", "c": "4469.8"}},
    {"complete": True, "volume": 95, "time": "2026-09-04T12:01:00.000000000Z",
     "mid": {"o": "4469.8", "h": "4471.0", "l": "4469.0", "c": "4470.5"}},
    {"complete": False, "volume": 10, "time": "2026-09-04T12:02:00.000000000Z",
     "mid": {"o": "4470.5", "h": "4470.6", "l": "4470.4", "c": "4470.5"}},
]}


class FakeResp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status
    def json(self):
        return self._p
    @property
    def text(self):
        return str(self._p)
    def raise_for_status(self):
        pass


class FakeHTTP:
    def __init__(self, *a, **k):
        pass
    def get(self, path, params=None):
        return FakeResp(CANDLES)
    def post(self, path, json=None):
        return FakeResp({"orderFillTransaction": {"id": "1"}})


@pytest.fixture(autouse=True)
def _fake_http(monkeypatch):
    monkeypatch.setattr(oamod.httpx, "Client", FakeHTTP)
    monkeypatch.setenv("OANDA_API_KEY", "test-key")
    monkeypatch.setenv("OANDA_ACCOUNT_ID", "test-acct")
    monkeypatch.delenv("LIVE_TRADING", raising=False)


def test_provider_maps_spot_and_skips_forming():
    cs = OandaProvider("k", "a").fetch_candles("XAU/USD", "1m", 10)
    assert len(cs) == 2  # forming candle dropped
    assert all(c.source_type == "SPOT" for c in cs)
    assert all(c.provider_instrument == "XAU_USD" for c in cs)
    assert cs[0].close == 4469.8 and cs[1].high == 4471.0


def test_oanda_first_in_chain_when_keyed(monkeypatch):
    from app.market_data import service as svc
    monkeypatch.setenv("OANDA_API_KEY", "test-key")
    svc._cache.clear()
    candles, meta = svc.get_candles("XAU/USD", "1m", 2)
    assert meta["source"] == "oanda" and meta["source_type"] == "SPOT"
    svc._cache.clear()


def test_live_order_refused_by_default():
    c = oamod.OandaClient("k", "a", "live")
    with pytest.raises(oamod.OandaError):
        c.market_order("XAU_USD", 100, confirm_live=True)
    r = client.post("/api/v1/brokers/oanda/order",
                    json={"instrument": "XAU_USD", "units": 100, "confirm_live": True})
    assert r.json()["filled"] is False and r.json()["dry_run"] is True


def test_broker_endpoints():
    assert client.get("/api/v1/brokers/oanda/health").status_code == 200
    assert len(client.get("/api/v1/brokers/oanda/candles?count=3").json()["candles"]) == 3
