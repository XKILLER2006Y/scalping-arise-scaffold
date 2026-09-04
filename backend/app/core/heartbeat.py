"""Heartbeat watchdog: container `Up` is not health, a fresh beat is.

The auto-trade loop calls beat() every iteration. Watchdogs (and humans via
GET /system/heartbeat) read status(): alive only if the last beat is younger
than max_age_s. Written to data/heartbeat.json (gitignored) for external
supervisors + echoed in the response.
"""
import json
import time
from pathlib import Path

FILE = Path(__file__).resolve().parents[2] / "data" / "heartbeat.json"


def beat(source: str = "auto-loop", info: dict | None = None) -> dict:
    payload = {"t": int(time.time()), "source": source, "info": info or {}}
    try:
        FILE.parent.mkdir(parents=True, exist_ok=True)
        FILE.write_text(json.dumps(payload))
    except Exception:
        pass
    return payload


def read_last() -> dict | None:
    try:
        return json.loads(FILE.read_text())
    except Exception:
        return None


def status(max_age_s: int = 90) -> dict:
    last = read_last()
    if not last:
        return {"alive": False, "age_s": None, "last": None,
                "reason": "no heartbeat ever recorded"}
    age = int(time.time()) - int(last.get("t", 0))
    alive = age <= max_age_s
    return {"alive": alive, "age_s": age, "last": last,
            "reason": None if alive else f"stale: last beat {age}s ago (limit {max_age_s}s)"}
