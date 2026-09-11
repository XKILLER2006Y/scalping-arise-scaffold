"""Audit progress stream: JSON-lines heartbeat so humans can WATCH long runs.

Zero effect on numbers: append-only side channel, failures swallowed.
Path from AUDIT_PROGRESS_FILE (default /tmp/audit_progress.jsonl).
Each line: {"t", "phase", "done", "total", "detail"}.
"""
from __future__ import annotations
import json
import os
import time

_counter = {"n": 0}


def emit(phase: str, done: int, total: int, detail: str = "") -> None:
    try:
        path = os.getenv("AUDIT_PROGRESS_FILE", "/tmp/audit_progress.jsonl")
        with open(path, "a") as f:
            f.write(json.dumps({"t": int(time.time()), "phase": phase,
                                "done": done, "total": total,
                                "pct": round(100 * done / total, 1) if total else 0.0,
                                "detail": detail[:160]}) + "\n")
    except Exception:
        pass


def reset() -> None:
    try:
        path = os.getenv("AUDIT_PROGRESS_FILE", "/tmp/audit_progress.jsonl")
        with open(path, "w") as f:
            f.write(json.dumps({"t": int(time.time()), "phase": "start",
                                "done": 0, "total": 100, "detail": "audit starting"}) + "\n")
    except Exception:
        pass
