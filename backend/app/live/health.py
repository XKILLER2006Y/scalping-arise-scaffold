"""Connection health: DISCONNECTED -> CONNECTED -> STALE/DEGRADED state machine
(adapted w/ permission from Hash-sudo-cell/scalping-arise
app/modules/market_data/live/connection_health.py, simplified to our chain:
no OANDA credentials here, health tracks data flow not sockets)."""
from __future__ import annotations
import threading
import time

STALE_AFTER_S = 180  # no closed 1m candle for 3 minutes = stale


class ConnectionHealth:
    def __init__(self, stale_after_s: int = STALE_AFTER_S):
        self._lock = threading.Lock()
        self._state = "DISCONNECTED"
        self._last_data_at: float | None = None
        self._last_error: str | None = None
        self._stale_after = stale_after_s

    def mark_connected(self) -> None:
        with self._lock:
            self._state = "CONNECTED"
            self._last_error = None

    def mark_data(self) -> None:
        with self._lock:
            self._last_data_at = time.time()
            if self._state in ("DISCONNECTED", "STALE"):
                self._state = "CONNECTED"

    def mark_error(self, err: str) -> None:
        with self._lock:
            self._last_error = str(err)[:200]

    def mark_degraded(self, reason: str) -> None:
        with self._lock:
            self._state = "DEGRADED"
            self._last_error = reason[:200]

    def status(self) -> dict:
        with self._lock:
            age = round(time.time() - self._last_data_at, 1) if self._last_data_at else None
            state = self._state
            if state == "CONNECTED" and age is not None and age > self._stale_after:
                state = "STALE"
            return {"state": state, "last_data_age_s": age,
                    "last_error": self._last_error, "stale_after_s": self._stale_after}
