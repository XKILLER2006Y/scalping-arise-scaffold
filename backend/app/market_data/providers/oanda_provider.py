"""OANDA market-data provider: XAU/USD SPOT (first in chain when keyed)."""
from app.brokers.oanda import OandaClient, GRANULARITY
from app.market_data.models import Candle, SourceType
from app.market_data.providers.base import BaseProvider


class OandaProvider(BaseProvider):
    name = "oanda"

    def __init__(self, api_key: str = "", account_id: str = "", env: str = "practice"):
        self.client = OandaClient(api_key, account_id, env)

    def fetch_candles(self, symbol: str = "XAU/USD", timeframe: str = "1m", limit: int = 100) -> list[Candle]:
        raw = self.client.candles("XAU_USD", GRANULARITY.get(timeframe, "M1"), limit)
        out: list[Candle] = []
        for c in raw:
            if not c.get("complete", True):
                continue  # forming candle: never feed incomplete bars downstream
            import datetime
            dt = datetime.datetime.fromisoformat(c["time"].replace("Z", "+00:00"))
            m = c["mid"]
            out.append(Candle(timestamp=int(dt.timestamp()), open=float(m["o"]), high=float(m["h"]),
                              low=float(m["l"]), close=float(m["c"]),
                              volume=float(c.get("volume", 0)) or None,
                              provider_instrument="XAU_USD", source="oanda",
                              source_type=SourceType.SPOT))
        if not out:
            raise RuntimeError("oanda returned no complete candles")
        return out
