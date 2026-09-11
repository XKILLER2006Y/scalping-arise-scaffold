"""Paper-forward loop: poll -> signal -> log -> settle. No execution, ever."""
from __future__ import annotations
import asyncio
import logging
import time

log = logging.getLogger("signal-bot.paper")
_loop = None


class PaperLoop:
    def __init__(self, symbol: str = "XAU/USD", poll_s: float = 60.0):
        self.symbol = symbol
        self.poll_s = poll_s
        self._running = False
        self._task = None
        self._cycles = 0
        self._last_error: str | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def status(self) -> dict:
        from app.core import store
        return {"running": self._running, "symbol": self.symbol, "poll_s": self.poll_s,
                "cycles": self._cycles, "last_error": self._last_error,
                "paper": store.paper_stats()}

    async def _run(self) -> None:
        from app.market_data.service import get_candles
        from app.system.engine import full_trace
        from app.signals.lifecycle import stamp_expiry, is_duplicate
        from app.paper.engine import settle_one
        from app.core import store
        from app.core.bus import get_bus
        while self._running:
            try:
                self._cycles += 1
                c1, _ = await asyncio.to_thread(get_candles, self.symbol, "1m", 250)
                c5, _ = await asyncio.to_thread(get_candles, self.symbol, "5m", 120)
                c15, _ = await asyncio.to_thread(get_candles, self.symbol, "15m", 120)
                if not c1:
                    continue
                trace = await asyncio.to_thread(full_trace, c1, c5, c15, self.symbol)
                sig, plan = trace.get("signal", {}), trace.get("trade_plan", {})
                if sig.get("action") in ("BUY", "SELL") and plan.get("feasible"):
                    sig = stamp_expiry(dict(sig), bar_ts=c1[-1].timestamp)
                    if not is_duplicate(sig):
                        store.log_paper_signal(sig, plan)
                        get_bus().emit({"type": "paper-signal", "symbol": self.symbol,
                                        "signal": sig, "trade_plan": plan})
                # Settle open signals against fresh bars.
                bars = [{"high": c.high, "low": c.low, "close": c.close} for c in c1[-70:]]
                for o in store.open_paper_signals():
                    st = settle_one(o, bars)
                    if st:
                        store.settle_paper_signal(st["id"], st["outcome"], st["exit_px"], st["r_mult"])
                        get_bus().emit({"type": "paper-settle", "symbol": self.symbol,
                                        "settlement": st})
                self._last_error = None
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._last_error = str(e)[:200]
                log.warning("paper loop error: %s", e)
            await asyncio.sleep(self.poll_s)


def get_loop() -> PaperLoop:
    global _loop
    if _loop is None:
        _loop = PaperLoop()
    return _loop
