"""Realtime + decision-hardening tests (patterns adapted w/ permission from friend)."""
from fastapi.testclient import TestClient
from app.main import app
from app.live.lifecycle import CandleLifecycle, period_start
from app.live.health import ConnectionHealth
from app.core.bus import EventBus
from app.signals.lifecycle import stamp_expiry, is_expired, is_duplicate, readiness

client = TestClient(app)


def test_lifecycle_closes_on_period_rollover():
    lc = CandleLifecycle("1m")
    base = 1_700_000_000 - (1_700_000_000 % 60)
    assert lc.update(base, 100.0) is None
    assert lc.update(base + 20, 101.0) is None
    assert lc.forming.high == 101.0
    closed = lc.update(base + 61, 102.0)
    assert closed is not None and closed.close == 101.0
    assert lc.closed_count == 1
    assert period_start(base + 61, "5m") % 300 == 0


def test_health_stale_detection():
    h = ConnectionHealth(stale_after_s=1000)
    assert h.status()["state"] == "DISCONNECTED"
    h.mark_connected()
    h.mark_data()
    assert h.status()["state"] == "CONNECTED"
    h2 = ConnectionHealth(stale_after_s=-1)
    h2.mark_connected()
    h2.mark_data()
    assert h2.status()["state"] == "STALE"


def test_bus_history_for_late_joiners():
    bus = EventBus()
    bus.emit({"type": "signal", "action": "BUY"})
    assert bus.history("signal")[0]["action"] == "BUY"
    assert bus.history("nope") == []


def test_signal_expiry_and_dedupe():
    s = stamp_expiry({"action": "BUY", "strategy": "X", "direction": "LONG"}, ttl_s=300, bar_ts=1)
    assert s["expires_at"] > s["issued_at"] and not is_expired(s)
    assert is_expired(s, now=s["expires_at"] + 1)
    assert is_duplicate(dict(s)) is False  # first alert passes
    assert is_duplicate(dict(s)) is True  # identical repeat suppressed
    assert is_duplicate({"action": "NO_TRADE"}) is False


def test_readiness_gate():
    ok = readiness({"source": "tradingview"}, "READY")
    assert ok["ready"] and ok["blocked_by"] is None
    bad = readiness({}, "WARMING_UP")
    assert not bad["ready"] and set(bad["blocked_by"]) == {"provider_up", "features_ready"}


def test_freshness_gate_rejects_stale_plans():
    from app.trade_planning.engine import create_plan
    sig = {"action": "BUY", "direction": "LONG"}
    r = create_plan(sig, 2650.0, 2.0, data_age_s=9999, max_age_s=120.0)
    assert r["feasible"] is False and "stale" in r["reason"]
    r2 = create_plan(sig, 2650.0, 2.0, data_age_s=10.0)
    assert "stale" not in str(r2.get("reason") or "")


def test_ws_endpoint_connects():
    with client.websocket_connect("/api/v1/ws") as ws:
        msg = ws.receive_text()
        assert "connected" in msg


def test_live_status_endpoints():
    assert client.get("/api/v1/live/status").status_code == 200
    assert client.get("/api/v1/signal?limit=50").status_code == 200


def test_no_lookahead_forming_bar_never_flows():
    """Guard concept (friend's look_ahead_guard): backtest input must equal
    closed bars only — appending the forming bar must not change decisions."""
    from app.market_data.resample import resample
    from app.market_data.providers.base import synth_candles
    from app.market_data.models import SourceType
    cs = synth_candles("twelve_data", "XAU/USD", SourceType.SPOT, n=65,
                       start=1_700_000_000 - (1_700_000_000 % 300))
    r5 = resample(cs, "5m")
    # resample drops the forming bucket: last closed 5m bar ends before last 1m bar
    assert r5[-1].timestamp < cs[-1].timestamp
