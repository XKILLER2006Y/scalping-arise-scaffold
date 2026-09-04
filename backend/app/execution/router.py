from fastapi import APIRouter, Body
from pydantic import BaseModel
from app.execution.engine import broker

router = APIRouter(prefix="/execution", tags=["execution"])

class CloseAllRequest(BaseModel):
    current_price: float | None = None

@router.get("/portfolio")
def get_portfolio():
    return broker.get_portfolio()

@router.post("/trade")
def execute_trade(plan: dict):
    return broker.execute_trade(plan)

@router.post("/close_all")
def close_all(current_price: float | None = None, req: CloseAllRequest | None = Body(None)):
    px = current_price
    if px is None and req is not None and req.current_price is not None:
        px = req.current_price
    if px is None:
        px = 2650.0
    return broker.close_all(px)
