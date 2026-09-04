"""OANDA v20 connector (practice-first). XAU/USD SPOT data + optional execution.

Safety doctrine (from research: execution gap + kill switches):
- Paper mode is the DEFAULT. Live orders require ALL of: LIVE_TRADING=true,
  OANDA_API_KEY + OANDA_ACCOUNT_ID set, OANDA_ENV=live explicitly, and
  confirm_live=True on the call. Anything less -> refusal, never a fill.
- Practice sandbox (api-fxpractice) mirrors production; start there.
- Timeouts on every call (no hanging the loop); 429s surface as errors.
"""
from __future__ import annotations
import os
import httpx

PRACTICE_REST = "https://api-fxpractice.oanda.com"
LIVE_REST = "https://api-fxtrade.oanda.com"
PRACTICE_STREAM = "https://stream-fxpractice.oanda.com"
LIVE_STREAM = "https://stream-fxtrade.oanda.com"

GRANULARITY = {"1m": "M1", "5m": "M5", "15m": "M15", "1h": "H1", "4h": "H4", "1d": "D"}


class OandaError(RuntimeError):
    pass


def live_trading_enabled() -> bool:
    return os.getenv("LIVE_TRADING", "false").lower() == "true"


class OandaClient:
    def __init__(self, api_key: str = "", account_id: str = "", env: str = "practice",
                 timeout: float = 10.0):
        self.api_key = api_key or os.getenv("OANDA_API_KEY", "")
        self.account_id = account_id or os.getenv("OANDA_ACCOUNT_ID", "")
        self.env = (env or os.getenv("OANDA_ENV", "practice")).lower()
        self.timeout = timeout
        base = LIVE_REST if self.env == "live" else PRACTICE_REST
        self._http = httpx.Client(base_url=base, timeout=timeout, headers={
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"})

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.account_id)

    def _get(self, path: str, params: dict | None = None) -> dict:
        if not self.api_key:
            raise OandaError("OANDA_API_KEY not set")
        r = self._http.get(path, params=params or {})
        if r.status_code == 429:
            raise OandaError("rate limited (429) — back off")
        if r.status_code >= 400:
            raise OandaError(f"{r.status_code}: {r.text[:200]}")
        return r.json()

    def candles(self, instrument: str = "XAU_USD", granularity: str = "M1",
                count: int = 500) -> list[dict]:
        """Oldest-first candle dicts. History back to 2005 on paid granularity."""
        js = self._get(f"/v3/instruments/{instrument}/candles",
                       {"granularity": granularity, "count": min(count, 5000)})
        return js.get("candles", [])

    def price(self, instruments: str = "XAU_USD") -> dict:
        if not self.account_id:
            raise OandaError("OANDA_ACCOUNT_ID not set")
        return self._get(f"/v3/accounts/{self.account_id}/pricing",
                         {"instruments": instruments})

    def account(self) -> dict:
        if not self.account_id:
            raise OandaError("OANDA_ACCOUNT_ID not set")
        return self._get(f"/v3/accounts/{self.account_id}")

    def transactions(self, count: int = 50) -> dict:
        if not self.account_id:
            raise OandaError("OANDA_ACCOUNT_ID not set")
        return self._get(f"/v3/accounts/{self.account_id}/transactions", {"count": count})

    def market_order(self, instrument: str, units: int, stop_loss: float | None = None,
                     take_profit: float | None = None, confirm_live: bool = False) -> dict:
        """Refuses unless live mode is fully armed (see module docstring)."""
        if not (live_trading_enabled() and self.env == "live" and self.configured and confirm_live):
            raise OandaError("live order refused: arm LIVE_TRADING=true + OANDA_ENV=live + token + confirm_live")
        order: dict = {"order": {"units": str(units), "instrument": instrument,
                                 "timeInForce": "FOK", "type": "MARKET", "positionFill": "DEFAULT"}}
        if stop_loss:
            order["order"]["stopLossOnFill"] = {"price": f"{stop_loss:.2f}"}
        if take_profit:
            order["order"]["takeProfitOnFill"] = {"price": f"{take_profit:.2f}"}
        r = self._http.post(f"/v3/accounts/{self.account_id}/orders", json=order)
        if r.status_code >= 400:
            raise OandaError(f"order rejected {r.status_code}: {r.text[:200]}")
        return r.json()
