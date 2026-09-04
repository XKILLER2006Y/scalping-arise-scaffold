"""Test hygiene: reset shared in-memory state between tests.

The API rate limiter (security._hits) and the candle cache are module-global.
Without reset, request counts accumulate across the whole pytest process and
later tests get 429s / stale cache hits depending on execution order.
"""
import pytest


@pytest.fixture(autouse=True)
def _reset_shared_state():
    from app.core import security
    security._hits.clear()
    from app.market_data import service as md_service
    with md_service._cache_lock:
        md_service._cache.clear()
    yield
    security._hits.clear()
    with md_service._cache_lock:
        md_service._cache.clear()
