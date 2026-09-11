"""Paper-forward loop tests: settlement math + divergence states."""
from app.paper.engine import settle_one, divergence

OPEN_LONG = {"id": 1, "direction": "LONG", "entry": 100.0, "stop": 98.0, "tp": 104.0}


def _bars(*triples):
    return [{"high": h, "low": l, "close": c} for h, l, c in triples]


def test_settle_long_win():
    r = settle_one(OPEN_LONG, _bars((101, 99, 100.5), (105, 100, 104.5)))
    assert r["outcome"] == "WIN" and r["exit_px"] == 104.0 and r["r_mult"] == 2.0


def test_settle_sl_wins_ties():
    # Both touched in one bar: conservative SL-first.
    r = settle_one(OPEN_LONG, _bars((105, 97, 103)))
    assert r["outcome"] == "LOSS" and r["exit_px"] == 98.0


def test_settle_short_and_timeout():
    o = {"id": 2, "direction": "SHORT", "entry": 100.0, "stop": 102.0, "tp": 96.0}
    r = settle_one(o, _bars((101, 99, 100), (97, 95, 96)))
    assert r["outcome"] == "WIN"
    r2 = settle_one(OPEN_LONG, _bars((101, 99.5, 100.5)) * 70, max_bars=60)
    assert r2["outcome"] == "TIME"


def test_settle_rejects_garbage():
    assert settle_one({"id": 3}, _bars((1, 1, 1))) is None
    assert settle_one(OPEN_LONG, []) is None


def test_divergence_states():
    assert divergence(0.5, 0.5, 30)["status"] == "ALIGNED"
    assert divergence(0.5, -0.5, 30)["status"] in ("DECAYING", "DIVERGED")
    assert divergence(0.5, -2.0, 30)["status"] == "DIVERGED"
    assert divergence(0.5, 0.0, 3)["status"] == "WARMING_UP"


def test_paper_endpoints():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    assert c.get("/api/v1/paper/health").status_code == 200
    assert c.get("/api/v1/paper/divergence").json()["status"] == "WARMING_UP"
