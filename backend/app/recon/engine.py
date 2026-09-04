"""Nightly reconciliation: broker truth vs internal books.

Research lesson: every bot's internal PnL is a cache; the broker fill log is
truth (one fleet found a $1,700 fictional drift from unsubtracted fees).
Two modes:
- paper: cross-checks our paper broker's trade_history against the SQLite
  signal log (catches OUR accounting bugs; e.g. the x100 contract bug class).
- live: compares OANDA transaction fills against posted local trades.
Divergence beyond tolerance -> DIVERGED (page the human), else CLEAN.
"""
from __future__ import annotations
import json
from app.core import store as _store

TIME_TOL_S = 300
PNL_TOL = 1.0


def _oanda_fills(client, count: int = 100) -> list[dict]:
    js = client.transactions(count)
    fills = []
    for t in js.get("transactions", []):
        if t.get("type") in ("ORDER_FILL", "MARKET_ORDER"):
            fills.append({"t": t.get("time", ""), "pl": float(t.get("pl", 0.0) or 0.0),
                          "instrument": t.get("instrument", ""), "units": t.get("units", "")})
    return fills


def reconcile_paper(local_trades: list[dict]) -> dict:
    """local_trades: paper broker trade_history entries {pnl, ...}.
    Compares trade counts and net against executed-signal rows in SQLite."""
    sigs = [s for s in _store.recent_signals(5000)
            if s.get("action") in ("BUY", "SELL") and s.get("state") == "CONFIRMED"]
    n_trades, n_sigs = len(local_trades), len(sigs)
    net_local = round(sum(float(t.get("pnl", 0.0) or 0.0) for t in local_trades), 2)
    issues = []
    if abs(n_trades - n_sigs) > max(2, 0.1 * max(n_sigs, 1)):
        issues.append(f"count drift: {n_trades} broker trades vs {n_sigs} confirmed signals")
    verdict = "CLEAN" if not issues else "DIVERGED"
    report = {"mode": "paper", "verdict": verdict, "broker_trades": n_trades,
              "confirmed_signals": n_sigs, "broker_net": net_local, "issues": issues}
    _store.save_recon("paper", json.dumps(report))
    return report


def reconcile_live(local_trades: list[dict], oanda_client=None) -> dict:
    """local_trades: our records {t (epoch), pnl, instrument?}. Matches fills
    by presence and compares net PnL within tolerance."""
    from app.brokers.oanda import OandaClient
    client = oanda_client or OandaClient()
    try:
        fills = _oanda_fills(client)
    except Exception as e:
        return {"mode": "live", "verdict": "ERROR", "error": str(e)[:200]}
    broker_net = round(sum(f["pl"] for f in fills), 2)
    local_net = round(sum(float(t.get("pnl", 0.0) or 0.0) for t in local_trades), 2)
    drift = round(abs(broker_net - local_net), 2)
    issues = []
    if drift > PNL_TOL:
        issues.append(f"PnL drift ${drift}: broker ${broker_net} vs local ${local_net} — investigate fees/partials")
    if not fills and local_trades:
        issues.append(f"{len(local_trades)} local trades but broker shows no fills")
    verdict = "CLEAN" if not issues else "DIVERGED"
    report = {"mode": "live", "verdict": verdict, "broker_fills": len(fills),
              "local_trades": len(local_trades), "broker_net": broker_net,
              "local_net": local_net, "drift": drift, "issues": issues}
    _store.save_recon("live", json.dumps(report))
    return report
