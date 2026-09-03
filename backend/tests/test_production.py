from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_reliability_and_forward():
    r = client.get("/api/v1/system/reliability")
    assert r.status_code == 200
    assert "counts" in r.json() and "no_trade_rate" in r.json()
    f = client.get("/api/v1/system/forward?limit=5")
    assert f.status_code == 200 and "entries" in f.json()

def test_docker_and_ci_present():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    assert (root / "docker-compose.yml").exists()
    assert (root / "backend" / "Dockerfile").exists()
    assert (root / "frontend" / "Dockerfile").exists()
    assert (root / ".github" / "workflows" / "ci.yml").exists()
