"""TradingView datafeed provider: OANDA:XAUUSD SPOT via TV's websocket feed.

Honesty notes (read before trusting this blindly):
- TradingView publishes NO official market-data REST API. This speaks their
  internal chart websocket protocol (same one the browser client uses).
  It works today, can break on any TV deploy, and bulk history pulls may be
  throttled. The provider chain treats TV as best-effort primary with
  automatic failover to Twelve Data -> yfinance.
- Free, no key. Symbol OANDA:XAUUSD (spot gold CFD feed).
- Only COMPLETE bars are returned; the forming bar is dropped (no look-ahead).
"""
import json
import random
import re
import time

from app.market_data.models import Candle, SourceType
from app.market_data.providers.base import BaseProvider

WS_URLS = [
    "wss://data.tradingview.com/socket.io/websocket",
    "wss://us01-data.tradingview.com/socket.io/websocket",
]

TV_INTERVAL = {"1m": "1", "5m": "5", "15m": "15"}
TOKEN = "unauthorized_user_token"


def _frames(payload: str) -> str:
    return f"~m~{len(payload)}~m~{payload}"


def _send(ws, method: str, params: list) -> None:
    ws.send(_frames(json.dumps({"m": method, "p": params}, separators=(",", ":"))))


def _parse_messages(raw: str):
    """Split ~m~ frames, yield parsed JSON payloads (skip ping frames)."""
    out = []
    for part in re.split(r"~m~\d+~m~", raw):
        if not part or part.startswith("~h"):
            continue
        try:
            out.append(json.loads(part))
        except Exception:
            continue
    return out


class TradingViewProvider(BaseProvider):
    name = "tradingview"

    def __init__(self, symbol: str = "OANDA:XAUUSD", timeout: float = 15.0):
        self.symbol = symbol
        self.timeout = timeout

    def fetch_candles(self, symbol: str = "XAU/USD", timeframe: str = "1m", limit: int = 100) -> list[Candle]:
        import websocket
        interval = TV_INTERVAL.get(timeframe, "1")
        need = min(max(limit, 10), 5000)
        bars: list[dict] = []
        loaded = False  # series_completed seen for the current request window
        deadline = time.time() + self.timeout
        token_suffix = "".join(random.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(12))
        session = f"qs_{token_suffix}"
        chart = f"cs_{token_suffix}"
        series = f"sds_{token_suffix[2:]}"
        last_err: Exception | None = None

        for url in WS_URLS:
            try:
                ws = websocket.create_connection(url, timeout=10)
                try:
                    _send(ws, "set_auth_token", [TOKEN])
                    _send(ws, "chart_create_session", [chart, ""])
                    _send(ws, "resolve_symbol", [chart, "sym", f'={{"symbol":"{self.symbol}","adjustment":"splits"}}'])
                    _send(ws, "create_series", [chart, series, "s1", "sym", interval, 300])
                    idle_rounds = 0
                    while time.time() < deadline:
                        try:
                            raw = ws.recv()
                        except Exception as e:
                            last_err = e
                            break
                        activity = False
                        for msg in _parse_messages(raw):
                            m = msg.get("m")
                            if m == "symbol_error":
                                raise RuntimeError(f"tradingview: invalid symbol ({msg.get('p')})")
                            if m in ("timescale_update", "du"):
                                p = msg.get("p", [])
                                payloads = p[1] if len(p) > 1 and isinstance(p[1], dict) else {}
                                for payload in payloads.values():
                                    if not isinstance(payload, dict):
                                        continue
                                    for b in payload.get("s", []) or []:
                                        v = b.get("v", [])
                                        if len(v) >= 6:
                                            bars.append({"t": int(v[0]), "o": v[1], "h": v[2],
                                                         "l": v[3], "c": v[4], "vol": v[5]})
                                            activity = True
                            if m == "series_completed":
                                loaded = True
                        if loaded and len(bars) >= need:
                            break
                        if loaded:
                            # Ask for the next older chunk until we have enough.
                            loaded = False
                            _send(ws, "request_more_data", [chart, series, 300])
                            continue
                        idle_rounds = idle_rounds + 1 if not activity else 0
                        if idle_rounds > 40:
                            break
                    ws.close()
                except Exception as e:
                    last_err = e
                    try:
                        ws.close()
                    except Exception:
                        pass
                if bars:
                    break
            except Exception as e:
                last_err = e
                continue

        if not bars:
            raise RuntimeError(f"tradingview feed failed: {last_err}")
        # Oldest-first, de-duplicated, complete bars only (drop the forming bar).
        seen, out = set(), []
        for b in sorted(bars, key=lambda x: x["t"]):
            if b["t"] in seen:
                continue
            seen.add(b["t"])
            out.append(Candle(timestamp=b["t"], open=b["o"], high=b["h"], low=b["l"],
                              close=b["c"], volume=float(b["vol"] or 0) or None,
                              provider_instrument=self.symbol, source="tradingview",
                              source_type=SourceType.SPOT))
        return out[:-1] if len(out) > 1 else out
