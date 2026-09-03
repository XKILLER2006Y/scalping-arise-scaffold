from enum import Enum
from pydantic import BaseModel, field_validator

class SourceType(str, Enum):
    SPOT = "SPOT"
    FUTURES_PROXY = "FUTURES_PROXY"

class Candle(BaseModel):
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    symbol: str = "XAU/USD"
    canonical_instrument: str = "XAU/USD"
    provider_instrument: str = "XAU/USD"
    source: str = "twelve_data"
    source_type: SourceType = SourceType.SPOT

    @field_validator("high")
    @classmethod
    def high_gte_low(cls, v, info):
        low = info.data.get("low")
        if low is not None and v < low:
            raise ValueError("high < low")
        return v
