from fastapi import APIRouter
from pydantic import BaseModel
from app.core import store as _store
from app.recon import engine as rec

router = APIRouter(prefix="/recon", tags=["recon"])

class RunReq(BaseModel):
    mode: str = "paper"  # paper | live
    local_trades: list[dict] = []

@router.get("/health")
def health():
    return {"status": "ok", "module": "recon",
            "rule": "broker fill log is truth; internal books are a cache"}

@router.post("/run")
def run(req: RunReq):
    if req.mode == "live":
        return rec.reconcile_live(req.local_trades)
    return rec.reconcile_paper(req.local_trades)

@router.get("/latest")
def latest():
    return _store.latest_recon() or {"report": None, "note": "no reconciliation run yet"}
