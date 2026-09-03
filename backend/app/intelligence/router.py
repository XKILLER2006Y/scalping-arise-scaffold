from fastapi import APIRouter
from pydantic import BaseModel
from app.intelligence.engine import is_blocked, record, status, exposure_guard

router = APIRouter(prefix="/intelligence", tags=["intelligence"])

class Rec(BaseModel):
    strategy: str
    pnl: float

@router.get("/health")
def health():
    return {"status": "ok", "module": "intelligence", "phase": 8}

@router.get("/news-check")
def news(now: int | None = None):
    return is_blocked(now)

@router.get("/exposure")
def expo(equity: float = 10000.0):
    return exposure_guard(equity)

@router.post("/record")
def rec(r: Rec):
    record(r.strategy, r.pnl)
    return status(r.strategy)

@router.get("/strategy/{name}")
def strat(name: str):
    return status(name)
