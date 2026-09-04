"""Wave 1 validation suite: walk-forward, Monte Carlo, sensitivity, benchmark, audit."""
from fastapi.testclient import TestClient
from app.main import app
from app.market_data.providers.base import synth_candles
from app.market_data.models import SourceType
from app.validation.engine import walk_forward, monte_carlo, sensitivity, benchmark_gate

client = TestClient(app)

def _cs(n=420):
    return [c.model_dump() for c in synth_candles("twelve_data", "XAU/USD", SourceType.SPOT, n=n)]

_GRID = {"sl_mult": [1.5], "tp_mult": [2.0], "min_conf": [60]}

def test_walk_forward_shape():
    r = client.post("/api/v1/validation/walk-forward", json={"candles": _cs(), "folds": 2, "grid": _GRID})
    j = r.json()
    assert r.status_code == 200
    assert "avg_wf_efficiency" in j and "verdict" in j and isinstance(j["folds"], list)

def test_monte_carlo_math():
    m = monte_carlo([10.0, -5.0, 8.0, -3.0, 12.0, -4.0] * 10, sims=200, seed=1, equity=10000.0)
    assert m["sims"] == 200 and 0 <= m["p_bad_path"] <= 1
    assert m["p95_max_dd_pct"] >= m["median_max_dd_pct"] >= 0
    assert m["verdict"] in ("ROBUST", "FRAGILE")
    e = monte_carlo([])
    assert e["verdict"] == "NO_TRADES"

def test_sensitivity_grid():
    r = client.post("/api/v1/validation/sensitivity", json={"candles": _cs(), "warmup": 200, "grid": _GRID})
    j = r.json()
    assert len(j["grid"]) == 1  # minimal grid for speed; default 3x3x3=27
    assert j["verdict"] in ("STABLE", "CLIFF_RISK")

def test_benchmark_gate():
    cs = synth_candles("twelve_data", "XAU/USD", SourceType.SPOT, n=100)
    g = benchmark_gate(cs, 500.0)
    assert "passed" in g and "bh_pnl" in g

def test_full_audit():
    r = client.post("/api/v1/validation/full-audit", json={"candles": _cs(), "folds": 2, "grid": _GRID})
    j = r.json()
    assert r.status_code == 200
    for k in ("base", "walk_forward", "monte_carlo", "sensitivity", "benchmark", "final_gate"):
        assert k in j
    assert j["final_gate"] in ("PROMOTE", "WAIT", "REJECT")
