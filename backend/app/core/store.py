"""SQLite persistence (stdlib, free). Survives restarts. Tables: signals, audit."""
import sqlite3
import time
import logging
from pathlib import Path

logger = logging.getLogger("scalping-arise.store")
DB = Path(__file__).resolve().parents[2] / "data" / "scalping.db"

_INIT_DONE = False

def _init_db():
    global _INIT_DONE
    if _INIT_DONE:
        return
    DB.parent.mkdir(parents=True, exist_ok=True)
    try:
        c = sqlite3.connect(str(DB), timeout=10.0)
        c.execute("PRAGMA journal_mode=WAL;")
        c.execute("PRAGMA synchronous=NORMAL;")
        c.execute("CREATE TABLE IF NOT EXISTS signals (id INTEGER PRIMARY KEY AUTOINCREMENT, t INTEGER, action TEXT, state TEXT, strategy TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, t INTEGER, event TEXT, detail TEXT)")
        c.commit()
        c.close()
        _INIT_DONE = True
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")

_init_db()

def _conn():
    _init_db()
    c = sqlite3.connect(str(DB), timeout=10.0)
    c.execute("PRAGMA busy_timeout=5000;")
    return c

def persist_signal(action: str, state: str | None, strategy: str | None):
    try:
        c = _conn()
        c.execute("INSERT INTO signals (t, action, state, strategy) VALUES (?,?,?,?)",
                  (int(time.time()), action, state, strategy))
        c.commit()
        c.close()
    except Exception as e:
        logger.error(f"Failed to persist signal: {e}")

def audit(event: str, detail: str = ""):
    try:
        c = _conn()
        c.execute("INSERT INTO audit (t, event, detail) VALUES (?,?,?)", (int(time.time()), event, detail[:500]))
        c.commit()
        c.close()
    except Exception as e:
        logger.error(f"Failed to persist audit event: {e}")

def signal_stats(limit: int = 10000) -> dict:
    try:
        c = _conn()
        rows = c.execute("SELECT action, COUNT(*) FROM signals GROUP BY action").fetchall()
        total_row = c.execute("SELECT COUNT(*) FROM signals").fetchone()
        total = total_row[0] if total_row else 0
        c.close()
        d = {a: n for a, n in rows}
        return {"counts": d, "total": total}
    except Exception as e:
        logger.error(f"Failed to fetch signal stats: {e}")
        return {"counts": {}, "total": 0}

