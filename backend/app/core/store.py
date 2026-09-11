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
        c.execute("""CREATE TABLE IF NOT EXISTS paper_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, t INTEGER, action TEXT, strategy TEXT,
            direction TEXT, entry REAL, stop REAL, tp REAL, confidence INTEGER,
            state TEXT, outcome TEXT DEFAULT 'OPEN', exit_px REAL, r_mult REAL)""")
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

def _enforce_retention(c, table: str, keep: int) -> None:
    """Tables grew forever (every trace persists). Cap rows so the DB can't
    fill the disk on a 24/7 loop. Single indexed DELETE, amortized per write."""
    try:
        c.execute(f"DELETE FROM {table} WHERE id <= (SELECT MAX(id) - ? FROM {table})", (keep,))
    except Exception as e:
        logger.error(f"Retention prune failed on {table}: {e}")


def persist_signal(action: str, state: str | None, strategy: str | None):
    try:
        c = _conn()
        c.execute("INSERT INTO signals (t, action, state, strategy) VALUES (?,?,?,?)",
                  (int(time.time()), action, state, strategy))
        _enforce_retention(c, "signals", 50000)
        c.commit()
        c.close()
    except Exception as e:
        logger.error(f"Failed to persist signal: {e}")

def audit(event: str, detail: str = ""):
    try:
        c = _conn()
        c.execute("INSERT INTO audit (t, event, detail) VALUES (?,?,?)", (int(time.time()), event, detail[:500]))
        _enforce_retention(c, "audit", 10000)
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



def recent_signals(limit: int = 500) -> list[dict]:
    try:
        c = _conn()
        rows = c.execute("SELECT t, action, state, strategy FROM signals ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        c.close()
        return [{"t": t, "action": a, "state": s, "strategy": st} for t, a, s, st in rows]
    except Exception:
        return []


def log_paper_signal(sig: dict, plan: dict) -> int | None:
    try:
        c = _conn()
        cur = c.execute(
            """INSERT INTO paper_signals
               (t, action, strategy, direction, entry, stop, tp, confidence, state)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (int(__import__("time").time()), sig.get("action"), sig.get("strategy"),
             sig.get("direction"), plan.get("entry"), plan.get("stop"),
             plan.get("take_profit"), sig.get("confidence"), sig.get("state")))
        c.commit()
        rid = cur.lastrowid
        c.close()
        return rid
    except Exception:
        return None


def open_paper_signals() -> list[dict]:
    try:
        c = _conn()
        rows = c.execute(
            "SELECT id, t, action, strategy, direction, entry, stop, tp FROM paper_signals "
            "WHERE outcome='OPEN' ORDER BY id").fetchall()
        c.close()
        return [{"id": r[0], "t": r[1], "action": r[2], "strategy": r[3],
                 "direction": r[4], "entry": r[5], "stop": r[6], "tp": r[7]} for r in rows]
    except Exception:
        return []


def settle_paper_signal(pid: int, outcome: str, exit_px: float, r_mult: float) -> None:
    try:
        c = _conn()
        c.execute("UPDATE paper_signals SET outcome=?, exit_px=?, r_mult=? WHERE id=?",
                  (outcome, exit_px, r_mult, pid))
        c.commit()
        c.close()
    except Exception:
        pass


def paper_stats() -> dict:
    try:
        c = _conn()
        rows = c.execute("SELECT outcome, COUNT(*), COALESCE(AVG(r_mult), 0) FROM paper_signals "
                         "WHERE outcome != 'OPEN' GROUP BY outcome").fetchall()
        open_n = c.execute("SELECT COUNT(*) FROM paper_signals WHERE outcome='OPEN'").fetchone()[0]
        c.close()
        by = {r[0]: {"n": r[1], "avg_r": round(r[2], 2)} for r in rows}
        wins = by.get("WIN", {}).get("n", 0)
        closed = sum(v["n"] for v in by.values())
        return {"by_outcome": by, "open": open_n, "closed": closed,
                "win_rate": round(wins / closed, 3) if closed else 0.0}
    except Exception:
        return {"by_outcome": {}, "open": 0, "closed": 0, "win_rate": 0.0}
