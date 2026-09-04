"""Scalping Arise backend. Full pipeline Phases 1-10, solo build."""
from fastapi import FastAPI
import asyncio
from contextlib import asynccontextmanager
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
from app.execution.router import router as execution_router
from app.brokers.router import router as brokers_router
from app.recon.router import router as recon_router

logger = get_logger("scalping-arise")
_START = __import__("time").time()

async def auto_trade_loop():
    import os
    import math
    from app.market_data.service import get_candles
    from app.market_analysis.engine import analyze_market, analyze
    from app.technical_features.engine import compute_features
    from app.strategy.engine import evaluate_all
    from app.signals.engine import decide
    from app.trade_planning.engine import create_plan, plan
    from app.execution.engine import broker
    from app.market_data.providers.base import synth_websocket_stream
    from app.market_data.models import SourceType
    from app.intelligence.sentiment import analyze_sentiment
    from app.intelligence.engine import exposure_guard

    # Pre-fetch historical candles
    try:
        history, _ = get_candles("XAU/USD", "1m", 250)
    except Exception as e:
        logger.error(f"Failed to prefetch candles: {e}")
        history = []

    reconnect_delay = float(os.environ.get("RECONNECT_DELAY", "1.0"))
    max_reconnect_delay = float(os.environ.get("MAX_RECONNECT_DELAY", "60.0"))
    import time as _t
    _last_beat = 0.0

    while True:
        try:
            stream = synth_websocket_stream("twelve_data", "XAU/USD", SourceType.SPOT)

            async for tick in stream:
                try:
                    # 1. Strict Tick Validation before appending to history
                    if (
                        tick is None
                        or getattr(tick, "open", None) is None
                        or getattr(tick, "high", None) is None
                        or getattr(tick, "low", None) is None
                        or getattr(tick, "close", None) is None
                        or getattr(tick, "timestamp", None) is None
                    ):
                        logger.warning(f"Dropping tick with missing fields: {tick}")
                        continue

                    try:
                        t_open = float(tick.open)
                        t_high = float(tick.high)
                        t_low = float(tick.low)
                        t_close = float(tick.close)
                        t_vol = float(getattr(tick, "volume", 0.0) or 0.0)
                    except (ValueError, TypeError):
                        logger.warning(f"Dropping non-numeric tick: {tick}")
                        continue

                    if (
                        math.isnan(t_open) or math.isnan(t_high) or math.isnan(t_low) or math.isnan(t_close)
                        or math.isinf(t_open) or math.isinf(t_high) or math.isinf(t_low) or math.isinf(t_close)
                        or t_open <= 0 or t_high <= 0 or t_low <= 0 or t_close <= 0
                        or t_high < t_low
                        or math.isnan(t_vol) or math.isinf(t_vol) or t_vol < 0
                    ):
                        logger.warning(f"Dropping corrupted/invalid tick: {tick}")
                        continue

                    history.append(tick)
                    if len(history) > 300:
                        history.pop(0)

                    # Heartbeat (throttled): proves the LOOP is alive, not just the container.
                    try:
                        from app.core.heartbeat import beat as _beat
                        now_b = _t.time()
                        if now_b - _last_beat >= 5.0:
                            _beat("auto-loop", {"history": len(history)})
                            _last_beat = now_b
                    except Exception:
                        pass
                    # Global kill switch: halt blocks new positions (existing logic exits via SL/TP).
                    try:
                        from app.core.halt import get_halt as _get_halt
                        _h = _get_halt()
                        if _h.get("halted"):
                            logger.warning(f"Trading halted, skipping tick: {_h.get('reason')}")
                            continue
                    except Exception:
                        pass
                        
                    # Persist tick to TimescaleDB
                    from app.market_data.db import db
                    # Using create_task to avoid blocking the event loop on insert
                    asyncio.create_task(
                        db.insert_tick(int(tick.timestamp), tick.symbol, t_close, t_vol, "twelve_data")
                    )

                    analysis = analyze_market(history[-120:])
                    analysis_dict = analysis.model_dump() if hasattr(analysis, "model_dump") else analysis

                    feats = compute_features(history[-220:], symbol="XAU/USD")
                    feat_dict = dict(feats["features"])
                    feat_dict["_volatility"] = feats.get("volatility")
                    feat_dict["volatility"] = feats.get("volatility")
                    close_px = t_close

                    sentiment = analyze_sentiment(feat_dict, analysis_dict)

                    ev = evaluate_all(analysis_dict, feat_dict, close_px)
                    closes = [c.close for c in history[-10:] if getattr(c, "close", None) is not None]
                    ctx = {"session": analysis_dict.get("session"), "closes": closes, "analysis": analysis_dict}
                    sig = decide(ev, feat_dict, ctx)

                    # Directional ML Alignment
                    action = sig.get("action")
                    direction = sig.get("direction")
                    ml_sent = sentiment.get("sentiment", "NEUTRAL")
                    raw_conf = float(sentiment.get("confidence", 50.0))

                    is_aligned = (direction == "LONG" and ml_sent == "BULLISH") or (direction == "SHORT" and ml_sent == "BEARISH")
                    is_conflicting = (direction == "LONG" and ml_sent == "BEARISH") or (direction == "SHORT" and ml_sent == "BULLISH")

                    if is_aligned:
                        ml_conf = raw_conf
                    elif is_conflicting:
                        ml_conf = 50.0
                    else:
                        ml_conf = 50.0

                    plan = create_plan(sig, close_px, feat_dict.get("atr14", 1.0), ml_confidence=ml_conf)
                    if plan.get("feasible") and action and action != "NO_TRADE":
                        if len(broker.open_positions) < 5:
                            guard_check = exposure_guard(broker.balance)
                            if guard_check.get("blocked"):
                                logger.info(f"Trade blocked by exposure guard: {guard_check.get('reason')}")
                                continue

                            if not plan.get("action"):
                                plan["action"] = action
                            if not plan.get("direction"):
                                plan["direction"] = direction
                            broker.execute_trade(plan)
                            
                    # Persist select advanced features and ml_conf
                    asyncio.create_task(db.insert_feature(int(tick.timestamp), tick.symbol, "ml_confidence", ml_conf))
                    if "gk_vol" in feat_dict:
                        asyncio.create_task(db.insert_feature(int(tick.timestamp), tick.symbol, "gk_vol", feat_dict["gk_vol"]))
                    if "cvd" in feat_dict:
                        asyncio.create_task(db.insert_feature(int(tick.timestamp), tick.symbol, "cvd", feat_dict["cvd"]))

                except asyncio.CancelledError:
                    raise
                except Exception as tick_err:
                    logger.error(f"Error processing auto-trade tick: {tick_err}")
                    continue

            # Clean generator exhaustion (e.g. in finite test streams)
            reconnect_delay = 1.0  # reset on clean exit
            break

        except asyncio.CancelledError:
            logger.info("Auto-trade loop cancelled gracefully.")
            raise
        except Exception as e:
            logger.error(f"Auto-trade loop error: {e}. Reconnecting in {reconnect_delay:.1f}s...")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)

@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.market_data.db import db
    try:
        await db.connect()
    except Exception as e:
        logger.warning(f"TimescaleDB unavailable, running without persistence: {e}")
    task = asyncio.create_task(auto_trade_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        try:
            await db.disconnect()
        except Exception:
            pass

def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="1.1.0", lifespan=lifespan)
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
        return {"status": "ok", "app": settings.app_name, "phase": "1-10-live",
                "warning": "Analysis only. Not financial advice."}

    @app.get("/api/v1/system/metrics")
    def metrics():
        import time
        from app.system.engine import reliability
        from app.market_data.service import provider_health
        return {"uptime_s": round(time.time() - _START, 1), "reliability": reliability(),
                "providers": provider_health()}

    for r in (market_data_router, market_analysis_router, technical_features_router,
              strategy_router, signals_router, trade_router, intel_router, backtest_router, system_router, execution_router,
              validation_router, brokers_router, recon_router):
        app.include_router(r, prefix="/api/v1")
    return app

app = create_app()
