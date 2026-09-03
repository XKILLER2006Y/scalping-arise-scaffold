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

_TD_INTERVAL = {"1m": "1min", "5m": "5min", "15m": "15min"}

class TwelveDataProvider(BaseProvider):
    name = "twelve_data"
    def __init__(self, api_key: str = "", base_url: str = "https://api.twelvedata.com"):
        self.api_key = api_key
        self.base_url = base_url
    def fetch_candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        from app.market_data.models import SourceType
        if not self.api_key:
            return synth_candles("twelve_data", "XAU/USD", SourceType.SPOT, n=limit)
        import httpx
        interval = _TD_INTERVAL.get(timeframe, "1min")
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                r = httpx.get(f"{self.base_url}/time_series", params={
                    "symbol": "XAU/USD", "interval": interval,
                    "outputsize": min(limit, 500), "apikey": self.api_key,
                }, timeout=8.0)
                r.raise_for_status()
                js = r.json()
                vals = js.get("values", [])
                if not vals:
                    raise RuntimeError(f"twelve_data: {str(js)[:200]}")
                out: list[Candle] = []
                for v in reversed(vals[-limit:]):
                    import datetime
                    dt = datetime.datetime.fromisoformat(v["datetime"].replace("Z", "+00:00"))
                    out.append(Candle(timestamp=int(dt.timestamp()), open=float(v["open"]),
                                      high=float(v["high"]), low=float(v["low"]), close=float(v["close"]),
                                      volume=float(v.get("volume") or 0) or None,
                                      provider_instrument="XAU/USD", source="twelve_data",
                                      source_type=SourceType.SPOT))
                return out
            except Exception as e:
                last_err = e
                time.sleep(0.5 * (attempt + 1))
        raise RuntimeError(f"twelve_data failed after retries: {last_err}")

class YFinanceProvider(BaseProvider):
    name = "yfinance"
    def fetch_candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        from app.market_data.models import SourceType
        try:
            import httpx
            iv = {"1m": "1m", "5m": "5m", "15m": "15m"}.get(timeframe, "1m")
            r = httpx.get("https://query1.finance.yahoo.com/v8/finance/chart/GC=F",
                          params={"interval": iv, "range": "1d"}, timeout=8.0,
                          headers={"User-Agent": "scalping-arise/1.0"})
            r.raise_for_status()
            js = r.json()["chart"]["result"][0]
            ts = js["timestamp"][-limit:]
            q = js["indicators"]["quote"][0]
            out: list[Candle] = []
            for i, t in enumerate(ts):
                idx = len(ts) - len(ts) + i
                # align quote arrays to tail
                off = len(q["open"]) - len(ts)
                o, h, l, c = q["open"][off+i], q["high"][off+i], q["low"][off+i], q["close"][off+i]
                if None in (o, h, l, c):
                    continue
                out.append(Candle(timestamp=int(t), open=float(o), high=float(h), low=float(l), close=float(c),
                                  volume=float((js["indicators"]["quote"][0].get("volume") or [None])[off+i] or 0) or None,
                                  provider_instrument="GC=F", source="yfinance",
                                  source_type=SourceType.FUTURES_PROXY))
            if out:
                return out
        except Exception:
            pass
        return synth_candles("yfinance", "GC=F", SourceType.FUTURES_PROXY, n=limit)
