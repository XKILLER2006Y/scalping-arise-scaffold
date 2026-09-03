"""Scalping Arise backend. Phases 1-4 CORE only. No Phase 4 extension, no Phase 5+."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import get_logger
from app.core.errors import app_exception_handler
from app.market_data.router import router as market_data_router
from app.market_analysis.router import router as market_analysis_router
from app.technical_features.router import router as technical_features_router

logger = get_logger("scalping-arise")

def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="0.4.0-core")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(Exception, app_exception_handler)

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "app": settings.app_name, "phase": "4-core"}

    app.include_router(market_data_router, prefix="/api/v1")
    app.include_router(market_analysis_router, prefix="/api/v1")
    app.include_router(technical_features_router, prefix="/api/v1")
    return app

app = create_app()
