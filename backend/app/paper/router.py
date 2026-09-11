from fastapi import APIRouter
from pydantic import BaseModel
from app.paper import engine as peng
from app.paper.loop import get_loop
from app.core import store

router = APIRouter(prefix="/paper", tags=["paper"])


class DivergeReq(BaseModel):
    backtest_expectancy_r: float = 0.0


@router.get("/health")
def health():
    return {"status": "ok", "module": "paper",
            "rule": "forward outcomes are truth; backtests are advertising until confirmed here"}


@router.post("/start")
async def start(poll_s: float = 60.0):
    loop = get_loop()
    loop.poll_s = poll_s
    await loop.start()
    return loop.status()


@router.post("/stop")
async def stop():
    await get_loop().stop()
    return get_loop().status()


@router.get("/status")
def status():
    return get_loop().status()


@router.get("/divergence")
def divergence(backtest_expectancy_r: float = 0.0):
    st = store.paper_stats()
    wins = st["by_outcome"].get("WIN", {}).get("n", 0)
    closed = st["closed"]
    avg_r = None
    if closed:
        tot = sum(v["n"] * v["avg_r"] for v in st["by_outcome"].values())
        avg_r = round(tot / closed, 2)
    if avg_r is None:
        return {"status": "WARMING_UP", "reason": "no settled forward signals yet"}
    return {"forward_avg_r": avg_r, "closed": closed,
            **peng.divergence(backtest_expectancy_r, avg_r, closed)}
