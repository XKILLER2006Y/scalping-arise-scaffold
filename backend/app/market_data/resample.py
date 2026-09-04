"""Timeframe resampling (1m -> 5m/15m). Closed buckets only: a bucket is emitted
only when a bar from the NEXT bucket arrives, so live use never leaks the
forming candle. Backtests slice resampled bars by timestamp for the same guarantee."""
from __future__ import annotations
from app.market_data.models import Candle

TF_SECONDS = {"1m": 60, "5m": 300, "15m": 900}


def resample(candles: list[Candle], timeframe: str) -> list[Candle]:
    secs = TF_SECONDS[timeframe]
    out: list[Candle] = []
    cur_key: int | None = None
    bucket: list[Candle] = []

    def flush():
        if not bucket:
            return
        b0 = bucket[0]
        out.append(Candle(
            timestamp=bucket[-1].timestamp, open=b0.open,
            high=max(c.high for c in bucket), low=min(c.low for c in bucket),
            close=bucket[-1].close,
            volume=sum(c.volume for c in bucket if c.volume) or None,
            symbol=b0.symbol, canonical_instrument=b0.canonical_instrument,
            provider_instrument=b0.provider_instrument, source=b0.source,
            source_type=b0.source_type))

    for c in candles:
        key = (c.timestamp // secs) * secs
        if cur_key is None:
            cur_key = key
        if key != cur_key:
            flush()  # previous bucket is closed: a bar from the next bucket arrived
            bucket = []
            cur_key = key
        bucket.append(c)
    # NOTE: trailing open bucket is deliberately NOT flushed (still forming).
    return out


def closed_asof(resampled: list[Candle], ts: int) -> list[Candle]:
    """Resampled bars with timestamp <= ts (all closed at ts). Binary search."""
    import bisect
    times = [c.timestamp for c in resampled]
    k = bisect.bisect_right(times, ts)
    return resampled[:k]
