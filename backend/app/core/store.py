"""SQLite persistence (stdlib, free). Survives restarts. Tables: signals, audit."""
import sqlite3
import time
from pathlib import Path

DB = Path(__file__).resolve().parents[2] / "data" / "scalping.db"

def _conn():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB))
    c.execute("CREATE TABLE IF NOT EXISTS signals (id INTEGER PRIMARY KEY AUTOINCREMENT, t INTEGER, action TEXT, state TEXT, strategy TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, t INTEGER, event TEXT, detail TEXT)")
    return c

def persist_signal(action: str, state: str | None, strategy: str | None):
    try:
        c = _conn()
        c.execute("INSERT INTO signals (t, action, state, strategy) VALUES (?,?,?,?)",
                  (int(time.time()), action, state, strategy))
        c.commit(); c.close()
    except Exception:
        pass

def audit(event: str, detail: str = ""):
    try:
        c = _conn()
        c.execute("INSERT INTO audit (t, event, detail) VALUES (?,?,?)", (int(time.time()), event, detail[:500]))
        c.commit(); c.close()
    except Exception:
        pass

def signal_stats(limit: int = 10000) -> dict:
    try:
        c = _conn()
        rows = c.execute("SELECT action, COUNT(*) FROM signals GROUP BY action").fetchall()
        total = c.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        c.close()
        d = {a: n for a, n in rows}
        return {"counts": d, "total": total}
    except Exception:
        return {"counts": {}, "total": 0}
