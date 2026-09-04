"""Scalping Arise — XAU/USD signal bot. Past + live market data in, BUY/SELL signals out.

No execution. No brokers. No auto-trading. This service analyses and signals;
a human (or another system) decides what to do with the signal.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging import get_logger
from app.core.errors import app_exception_handler
from app.core.middleware import request_id_log
from app.core.security import guard
from app.market_data.router import router as market_data_router
from app.market_analysis.router import router as market_analysis_router
from app.technical_features.router import router as technical_features_router
from app.strategy.router import router as strategy_router
from app.signals.router import router as signals_router
from app.trade_planning.router import router as trade_router
from app.intelligence.router import router as intel_router
from app.backtesting.router import router as backtest_router
from app.system.router import router as system_router
from app.validation.router import router as validation_router

logger = get_logger("signal-bot")
_START = __import__("time").time()

SYMBOL = "XAU/USD"


def create_app() -> FastAPI:
    app = FastAPI(title=f"{settings.app_name} — XAU/USD Signal Bot", version="2.0.0-signal")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(guard)
    app.middleware("http")(request_id_log)
    app.add_exception_handler(Exception, app_exception_handler)

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "app": settings.app_name, "mode": "signal-bot",
                "symbol": SYMBOL, "warning": "Signals only. Not financial advice. No auto-execution."}

    @app.get("/api/v1/system/metrics")
    def metrics():
        import time
        from app.system.engine import reliability
        from app.market_data.service import provider_health
        return {"uptime_s": round(time.time() - _START, 1), "reliability": reliability(),
                "providers": provider_health()}

    @app.get("/api/v1/signal", tags=["signal"])
    def signal(symbol: str = SYMBOL, limit: int = 250, equity: float = 10000.0,
               risk_pct: float = 1.0, spread: float = 0.3):
        """One call: past + live XAU/USD data in, BUY/SELL/NO_TRADE signal out."""
        from app.system.engine import full_trace
        from app.market_data.service import get_candles
        c1, m1 = get_candles(symbol, "1m", limit)
        c5, _ = get_candles(symbol, "5m", limit)
        c15, _ = get_candles(symbol, "15m", limit)
        out = full_trace(c1, c5, c15, symbol, equity, risk_pct, spread)
        out["data_meta"] = m1
        return out

    for r in (market_data_router, market_analysis_router, technical_features_router,
              strategy_router, signals_router, trade_router, intel_router, backtest_router,
              system_router, validation_router):
        app.include_router(r, prefix="/api/v1")
    return app

app = create_app()
