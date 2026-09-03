"""Provider abstraction. Twelve Data = SPOT, yfinance GC=F = FUTURES_PROXY."""
from abc import ABC, abstractmethod
from app.market_data.models import Candle
import time

class BaseProvider(ABC):
    name: str = "base"
    @abstractmethod
    def fetch_candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        raise NotImplementedError

def synth_candles(source: str, provider_instrument: str, source_type, n: int = 100, start: int | None = None) -> list[Candle]:
    # Deterministic synthetic candles for offline baseline + tests. No network.
    if start is None:
        start = int(time.time()) - n * 60
    out: list[Candle] = []
    price = 2650.0
    for i in range(n):
        drift = ((i * 37) % 11 - 5) * 0.35
        o = price
        c = price + drift
        h = max(o, c) + 0.4
        l = min(o, c) - 0.4
        out.append(Candle(
            timestamp=start + i * 60, open=o, high=h, low=l, close=c,
            volume=1000 + (i * 13) % 500,
            provider_instrument=provider_instrument, source=source, source_type=source_type,
        ))
        price = c
    return out

class TwelveDataProvider(BaseProvider):
    name = "twelve_data"
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
    def fetch_candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        # Offline scaffold: deterministic SPOT candles. Live key wiring comes later.
        from app.market_data.models import SourceType
        return synth_candles("twelve_data", "XAU/USD", SourceType.SPOT, n=limit)

class YFinanceProvider(BaseProvider):
    name = "yfinance"
    def fetch_candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        # GC=F must NEVER masquerade as spot.
        from app.market_data.models import SourceType
        return synth_candles("yfinance", "GC=F", SourceType.FUTURES_PROXY, n=limit)
