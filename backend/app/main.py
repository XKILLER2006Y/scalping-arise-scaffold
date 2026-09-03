"""Scalping Arise backend. Scaffold-only full pipeline Phases 1-10. Friend's repo stays joint-locked."""
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

logger = get_logger("scalping-arise")
_START = __import__("time").time()

def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="1.0.0-enterprise-scaffold")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(request_id_log)
    app.middleware("http")(guard)
    app.add_exception_handler(Exception, app_exception_handler)

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "app": settings.app_name, "phase": "1-10-enterprise-scaffold",
                "warning": "Scaffold only. Not financial advice."}

    @app.get("/api/v1/system/metrics")
    def metrics():
        import time
        from app.system.engine import reliability
        from app.market_data.service import provider_health
        return {"uptime_s": round(time.time() - _START, 1), "reliability": reliability(),
                "providers": provider_health()}

    for r in (market_data_router, market_analysis_router, technical_features_router,
              strategy_router, signals_router, trade_router, intel_router, backtest_router, system_router):
        app.include_router(r, prefix="/api/v1")
    return app

app = create_app()
