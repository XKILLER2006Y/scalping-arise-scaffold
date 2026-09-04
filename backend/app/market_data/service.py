"""Normalization, validation, caching, failover, freshness, gaps. No look-ahead."""
import threading
import time
from collections import OrderedDict
from app.core.config import settings
from app.market_data.models import Candle
from app.market_data.providers.base import TwelveDataProvider, YFinanceProvider

# LRU + TTL cache (eviction pattern adapted w/ permission from
# Hash-sudo-cell/scalping-arise backend/app/modules/market_data/cache.py).
_CACHE_MAX_ENTRIES = 32
_cache: OrderedDict[str, tuple[float, list[Candle]]] = OrderedDict()
_cache_lock = threading.Lock()


def _cache_get(k: str):
    with _cache_lock:
        if k in _cache:
            _cache.move_to_end(k)
            return _cache[k]
    return None


def _cache_put(k: str, val: tuple[float, list[Candle]]):
    with _cache_lock:
        if k in _cache:
            _cache.pop(k)
        _cache[k] = val
        while len(_cache) > _CACHE_MAX_ENTRIES:
            _cache.popitem(last=False)


def cache_stats() -> dict:
    with _cache_lock:
        return {"entries": len(_cache), "max_entries": _CACHE_MAX_ENTRIES,
                "keys": list(_cache.keys())}
_provider_health: dict[str, dict] = {
    "twelve_data": {"ok": True, "fails": 0, "latency_ms": None, "mode": "demo-or-live"},
    "yfinance": {"ok": True, "fails": 0, "latency_ms": None, "mode": "live-or-demo"},
}

def _key(symbol: str, tf: str) -> str:
    return f"{symbol}|{tf}"

def validate_candles(candles: list[Candle], timeframe: str = "1m") -> list[str]:
    issues: list[str] = []
    seen = set()
    for c in candles:
        if c.timestamp in seen:
            issues.append(f"duplicate:{c.timestamp}")
        seen.add(c.timestamp)
        if not (c.low <= c.open <= c.high and c.low <= c.close <= c.high):
            issues.append(f"ohlc-invalid:{c.timestamp}")
    ts = sorted(seen)
    if len(ts) >= 2:
        interval = settings.tf_interval_seconds.get(timeframe, 60)
        for a, b in zip(ts, ts[1:]):
            if b - a > interval * 2:
                issues.append(f"gap:{a}->{b}")
    return issues

def provider_health() -> dict:
    return _provider_health

def get_candles(symbol: str = "XAU/USD", timeframe: str = "1m", limit: int = 100) -> tuple[list[Candle], dict]:
    k = _key(symbol, timeframe)
    now = time.time()
    hit = _cache_get(k)
    if hit and now - hit[0] < settings.cache_ttl_seconds:
        cached_list = hit[1]
        if len(cached_list) >= limit:
            out = cached_list[-limit:]
            age = now - out[-1].timestamp if out else 0
            meta = {
                "cached": True,
                "source": out[0].source if out else None,
                "source_type": out[0].source_type if out else None,
                "fresh": age <= settings.freshness_max_age_seconds,
                "age_seconds": round(age, 1),
            }
            issues = validate_candles(out, timeframe)
            if issues:
                meta["validation_issues"] = issues[:10]
            return out, meta

    t0 = time.time()
    fetch_limit = max(limit, 250)
    primary = TwelveDataProvider(settings.twelve_data_api_key, settings.twelve_data_base_url)
    try:
        candles = primary.fetch_candles(symbol, timeframe, fetch_limit)
        ms = round((time.time() - t0) * 1000, 1)
        _provider_health["twelve_data"] = {"ok": True, "fails": 0, "latency_ms": ms,
                                           "mode": "live" if settings.twelve_data_api_key else "demo-synthetic"}
        meta = {"cached": False, "source": "twelve_data", "source_type": "SPOT", "failover": False}
    except Exception as e:
        ms = round((time.time() - t0) * 1000, 1)
        _provider_health["twelve_data"] = {"ok": False, "fails": _provider_health["twelve_data"].get("fails", 0) + 1,
                                           "latency_ms": ms, "error": str(e)[:200]}
        t1 = time.time()
        fallback = YFinanceProvider()
        candles = fallback.fetch_candles(symbol, timeframe, fetch_limit)
        ms2 = round((time.time() - t1) * 1000, 1)
        _provider_health["yfinance"] = {"ok": True, "fails": 0, "latency_ms": ms2, "mode": "fallback"}
        meta = {"cached": False, "source": "yfinance", "source_type": "FUTURES_PROXY", "failover": True}
    _cache_put(k, (now, candles))
    out = candles[-limit:]
    if out:
        age = now - out[-1].timestamp
        meta["fresh"] = age <= settings.freshness_max_age_seconds
        meta["age_seconds"] = round(age, 1)
    issues = validate_candles(out, timeframe)
    if issues:
        meta["validation_issues"] = issues[:10]
    return out, meta
