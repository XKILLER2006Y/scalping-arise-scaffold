"""Live signal manager: poll provider chain -> lifecycles -> signal on every 1m close.

No OANDA credentials needed: polls get_candles (TV -> Twelve -> yfinance),
derives a tick from the latest close, and lets CandleLifecycle decide when a
real 1m period rolled over. Only CLOSED candles trigger signal recompute —
the forming bar never leaks downstream (same guarantee as the backtester).
Emits {"type": "signal", ...} on the event bus for WS clients + history.
"""
from __future__ import annotations
import asyncio
import logging
import time

log = logging.getLogger("signal-bot.live")

_manager = None


class LiveManager:
    def __init__(self, symbol: str = "XAU/USD", poll_s: float = 10.0):
        from app.live.lifecycle import CandleLifecycle
        from app.live.health import ConnectionHealth
        self.symbol = symbol
        self.poll_s = poll_s
        self._lifecycles = {tf: CandleLifecycle(tf, symbol) for tf in ("1m", "5m", "15m")}
        self._health = ConnectionHealth()
        self._running = False
        self._task = None
        self._last_signal = None

    @property
    def health(self):
        return self._health

    @property
    def last_signal(self):
        return self._last_signal

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._health.mark_connected()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        from app.market_data.service import get_candles
        from app.system.engine import full_trace
        from app.core.bus import get_bus
        while self._running:
            try:
                candles, meta = await asyncio.to_thread(get_candles, self.symbol, "1m", 250)
                if not candles:
                    self._health.mark_error("empty poll")
                    await asyncio.sleep(self.poll_s)
                    continue
                last = candles[-1]
                closed = self._lifecycles["1m"].update(
                    last.timestamp, last.close, last.volume,
                    source=last.source, source_type=last.source_type,
                    provider_instrument=last.provider_instrument)
                self._health.mark_data()
                if closed is not None:
                    # Fresh 1m close: full MTF recompute + signal.
                    c1, _ = await asyncio.to_thread(get_candles, self.symbol, "1m", 250)
                    c5, _ = await asyncio.to_thread(get_candles, self.symbol, "5m", 120)
                    c15, _ = await asyncio.to_thread(get_candles, self.symbol, "15m", 120)
                    trace = await asyncio.to_thread(full_trace, c1, c5, c15, self.symbol)
                    self._last_signal = {"t": int(time.time()), **trace.get("signal", {})}
                    get_bus().emit({"type": "signal", "symbol": self.symbol,
                                    "signal": trace.get("signal"),
                                    "trade_plan": trace.get("trade_plan"),
                                    "market": trace.get("market")})
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("live loop error: %s", e)
                self._health.mark_error(str(e))
            await asyncio.sleep(self.poll_s)

    def status(self) -> dict:
        return {"running": self._running, "symbol": self.symbol,
                "poll_s": self.poll_s, "health": self._health.status(),
                "closed_1m": self._lifecycles["1m"].closed_count,
                "last_signal": self._last_signal}


def get_manager() -> LiveManager:
    global _manager
    if _manager is None:
        _manager = LiveManager()
    return _manager
