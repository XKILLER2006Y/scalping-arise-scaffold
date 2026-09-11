"""In-process event bus (adapted w/ permission from Hash-sudo-cell/scalping-arise
app/modules/events.py): pub/sub with history for late joiners. Sync handlers
kept simple for our stack (no async fan-out needed at our scale)."""
from __future__ import annotations
import threading
import time
from collections import defaultdict

_bus = None
_lock = threading.Lock()


class EventBus:
    def __init__(self, max_history: int = 100):
        self._subs: dict[str, list] = defaultdict(list)
        self._history: dict[str, list] = defaultdict(list)
        self._max = max_history
        self._hlock = threading.Lock()

    def subscribe(self, event_type: str, handler) -> None:
        with self._hlock:
            self._subs[event_type].append(handler)

    def emit(self, event: dict) -> None:
        event = dict(event)
        event.setdefault("t", int(time.time()))
        et = event.get("type", "unknown")
        with self._hlock:
            self._history[et].append(event)
            self._history[et] = self._history[et][-self._max :]
            handlers = list(self._subs.get(et, [])) + list(self._subs.get("*", []))
        for h in handlers:
            try:
                h(event)
            except Exception:
                pass

    def history(self, event_type: str, limit: int = 50) -> list[dict]:
        with self._hlock:
            return list(self._history.get(event_type, [])[-limit:])


def get_bus() -> EventBus:
    global _bus
    with _lock:
        if _bus is None:
            _bus = EventBus()
        return _bus
