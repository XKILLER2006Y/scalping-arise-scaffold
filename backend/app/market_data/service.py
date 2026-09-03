"""Normalization, validation, caching, failover, freshness, gaps. No look-ahead."""
import time
from app.core.config import settings
from app.market_data.models import Candle
from app.market_data.providers.base import TwelveDataProvider, YFinanceProvider

_cache: dict[str, tuple[float, list[Candle]]] = {}
_provider_health: dict[str, dict] = {"twelve_data": {"ok": True}, "yfinance": {"ok": True}}

def _key(symbol: str, tf: str) -> str:
    return f"{symbol}|{tf}"

def validate_candles(candles: list[Candle]) -> list[str]:
    issues: list[str] = []
    seen = set()
    for c in candles:
        if c.timestamp in seen:
            issues.append(f"duplicate:{c.timestamp}")
        seen.add(c.timestamp)
        if not (c.low <= c.open <= c.high and c.low <= c.close <= c.high):
            issues.append(f"ohlc-invalid:{c.timestamp}")
    # gap detection (sorted)
    ts = sorted(seen)
    if len(ts) >= 2:
        interval = settings.tf_interval_seconds.get("1m", 60)
        for a, b in zip(ts, ts[1:]):
            if b - a > interval * 2:
                issues.append(f"gap:{a}->{b}")
    return issues

def get_candles(symbol: str = "XAU/USD", timeframe: str = "1m", limit: int = 100) -> tuple[list[Candle], dict]:
    k = _key(symbol, timeframe)
    now = time.time()
    if k in _cache and now - _cache[k][0] < settings.cache_ttl_seconds:
        candles = _cache[k][1][:limit]
        return candles, {"cached": True, "source": candles[0].source if candles else None,
                         "source_type": candles[0].source_type if candles else None}
    primary = TwelveDataProvider(settings.twelve_data_api_key)
    try:
        candles = primary.fetch_candles(symbol, timeframe, limit)
        meta = {"cached": False, "source": "twelve_data", "source_type": "SPOT", "failover": False}
        _provider_health["twelve_data"] = {"ok": True}
    except Exception:
        _provider_health["twelve_data"] = {"ok": False}
        fallback = YFinanceProvider()
        candles = fallback.fetch_candles(symbol, timeframe, limit)
        meta = {"cached": False, "source": "yfinance", "source_type": "FUTURES_PROXY", "failover": True}
    _cache[k] = (now, candles)
    # freshness
    if candles:
        age = now - candles[-1].timestamp
        meta["fresh"] = age <= settings.freshness_max_age_seconds
        meta["age_seconds"] = round(age, 1)
    issues = validate_candles(candles)
    if issues:
        meta["validation_issues"] = issues[:10]
    return candles[:limit], meta
