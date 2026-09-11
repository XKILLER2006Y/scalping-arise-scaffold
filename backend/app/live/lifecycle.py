"""Candle lifecycle: FORMING -> CLOSED per timeframe (adapted w/ permission from
Hash-sudo-cell/scalping-arise app/modules/market_data/live/candle_lifecycle.py,
rewritten for our epoch-timestamp Candle model).

A tick either updates the forming candle (same period) or closes it and starts
a new one (new period). Closed candles are the ONLY thing that flows downstream.
"""
from __future__ import annotations
from app.market_data.models import Candle, SourceType

TF_SECONDS = {"1m": 60, "5m": 300, "15m": 900}


def period_start(ts: int, timeframe: str) -> int:
    secs = TF_SECONDS[timeframe]
    return (ts // secs) * secs


class CandleLifecycle:
    def __init__(self, timeframe: str, symbol: str = "XAU/USD"):
        self.timeframe = timeframe
        self.symbol = symbol
        self._current: Candle | None = None
        self._last_ts: int | None = None
        self.closed_count = 0

    @property
    def forming(self) -> Candle | None:
        return self._current

    def update(self, ts: int, price: float, volume: float | None = None,
               source: str = "live", source_type: SourceType = SourceType.SPOT,
               provider_instrument: str = "XAU/USD") -> Candle | None:
        """Feed a tick. Returns the CLOSED candle on period rollover, else None."""
        if self._current is None:
            self._current = Candle(timestamp=period_start(ts, self.timeframe), open=price,
                                   high=price, low=price, close=price, volume=volume,
                                   symbol=self.symbol, provider_instrument=provider_instrument,
                                   source=source, source_type=source_type)
            self._last_ts = ts
            return None
        if period_start(ts, self.timeframe) > period_start(self._last_ts, self.timeframe):
            closed = self._current
            self.closed_count += 1
            self._current = Candle(timestamp=period_start(ts, self.timeframe), open=price,
                                   high=price, low=price, close=price, volume=volume,
                                   symbol=self.symbol, provider_instrument=provider_instrument,
                                   source=source, source_type=source_type)
            self._last_ts = ts
            return closed
        c = self._current
        self._current = Candle(timestamp=c.timestamp, open=c.open,
                               high=max(c.high, price), low=min(c.low, price),
                               close=price,
                               volume=((c.volume or 0) + (volume or 0)) if volume else c.volume,
                               symbol=c.symbol, provider_instrument=c.provider_instrument,
                               source=c.source, source_type=c.source_type)
        self._last_ts = ts
        return None

    def reset(self) -> None:
        self._current = None
        self._last_ts = None
