from fastapi import APIRouter, Query
from pydantic import BaseModel
from app.brokers.oanda import OandaClient, OandaError, live_trading_enabled

router = APIRouter(prefix="/brokers/oanda", tags=["brokers-oanda"])

class OrderReq(BaseModel):
    instrument: str = "XAU_USD"
    units: int = 100
    stop_loss: float | None = None
    take_profit: float | None = None
    confirm_live: bool = False  # must be true AND server armed, else refusal

@router.get("/health")
def health():
    c = OandaClient()
    return {"status": "ok", "module": "oanda", "env": c.env,
            "configured": c.configured, "live_armed": live_trading_enabled()}

@router.get("/price")
def price(instruments: str = "XAU_USD"):
    try:
        return OandaClient().price(instruments)
    except OandaError as e:
        return {"error": str(e)}

@router.get("/account")
def account():
    try:
        return OandaClient().account()
    except OandaError as e:
        return {"error": str(e)}

@router.get("/candles")
def candles(instrument: str = "XAU_USD", granularity: str = "M1", count: int = Query(100, le=5000)):
    try:
        return {"candles": OandaClient().candles(instrument, granularity, count)}
    except OandaError as e:
        return {"error": str(e)}

@router.post("/order")
def order(req: OrderReq):
    """Dry-run preview by default. Live fill ONLY when fully armed + confirm_live."""
    if not (live_trading_enabled() and confirm_live and req.confirm_live):
        return {"filled": False, "dry_run": True,
                "would_send": req.model_dump(),
                "reason": "paper mode: set LIVE_TRADING=true, OANDA_ENV=live, token + confirm_live to arm"}
    try:
        return {"filled": True, "dry_run": False,
                "result": OandaClient().market_order(req.instrument, req.units,
                                                     req.stop_loss, req.take_profit, True)}
    except OandaError as e:
        return {"filled": False, "error": str(e)}
