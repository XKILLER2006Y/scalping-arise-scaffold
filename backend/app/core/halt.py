"""Global trading halt — the human kill switch.

Checked by the paper broker AND the auto-trade loop before any new position.
Persists to the SQLite audit log so halts survive restarts and stay reviewable.
"""
import threading
import time
from app.core import store as _store

_lock = threading.Lock()
_STATE = {"halted": False, "reason": None, "since": None}


def set_halt(halted: bool, reason: str = "") -> dict:
    with _lock:
        _STATE.update({"halted": bool(halted),
                       "reason": reason or None,
                       "since": int(time.time()) if halted else None})
        try:
            _store.audit("HALT_ON" if halted else "HALT_OFF", reason[:500])
        except Exception:
            pass
        return dict(_STATE)


def get_halt() -> dict:
    with _lock:
        return dict(_STATE)
