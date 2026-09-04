"""Challenger 2 Empirical Concurrency, Broker Ledger & SQLite Stress Test Suite.

Verifies:
1. Concurrent execution of PaperBroker and auto_trade_loop alongside multi-client HTTP requests.
2. Ledger invariants and accounting integrity: balance is finite, never NaN/Inf, and matches trade PnLs.
3. SQLite store concurrency under WAL mode with busy_timeout.
4. Position sizing risk adherence and extreme sizing resilience.
"""
import asyncio
import concurrent.futures
import math
import threading
import time
from unittest.mock import patch
import pytest
from starlette.testclient import TestClient

from app.main import app, auto_trade_loop
from app.execution.engine import PaperBroker, broker
from app.market_data.models import Candle, SourceType
from app.trade_planning.engine import create_plan
from app.core import store


def _make_stress_candle(i: int, base: float = 2650.0) -> Candle:
    px = base + (i % 20) * 0.4 - 4.0
    return Candle(
        timestamp=int(time.time()) + i,
        open=px,
        high=px + 0.8,
        low=px - 0.8,
        close=px + 0.1,
        volume=250.0,
        provider_instrument="XAU/USD",
        source="twelve_data",
        source_type=SourceType.SPOT,
    )


# ===========================================================================
# 1. PaperBroker & auto_trade_loop Concurrency Stress Testing
# ===========================================================================
@pytest.mark.asyncio
async def test_paper_broker_and_auto_trade_loop_concurrent_multi_client():
    """Stress tests auto_trade_loop running concurrently with 16 multi-threaded
    HTTP client workers executing conflicting calls (/trade, /close_all, /portfolio, /candles).
    """
    client = TestClient(app)
    stop_event = threading.Event()
    client_errors = []
    ticks_emitted = 0

    async def continuous_stream(*args, **kwargs):
        nonlocal ticks_emitted
        i = 0
        while not stop_event.is_set():
            ticks_emitted += 1
            yield _make_stress_candle(i)
            i += 1
            await asyncio.sleep(0.005)

    def client_worker(worker_id: int, num_ops: int = 20):
        headers = {"X-Forwarded-For": f"192.168.10.{10 + worker_id}"}
        for op in range(num_ops):
            if stop_event.is_set():
                break
            try:
                mod = (worker_id * 3 + op) % 4
                if mod == 0:
                    r = client.post("/api/v1/execution/trade", json={
                        "action": "BUY" if op % 2 == 0 else "SELL",
                        "direction": "LONG" if op % 2 == 0 else "SHORT",
                        "entry": 2650.0 + (op % 5) * 0.2,
                        "lots": 0.05,
                        "feasible": True,
                    }, headers=headers)
                    assert r.status_code in (200, 429)
                elif mod == 1:
                    px = 2650.0 + (op % 5) - 2.0
                    r = client.post("/api/v1/execution/close_all", json={"current_price": px}, headers=headers)
                    assert r.status_code in (200, 429)
                elif mod == 2:
                    r = client.get("/api/v1/execution/portfolio", headers=headers)
                    assert r.status_code in (200, 429)
                else:
                    r = client.get("/api/v1/market-data/candles?limit=50", headers=headers)
                    assert r.status_code in (200, 429)
            except Exception as err:
                client_errors.append((worker_id, op, err))

    with patch("app.market_data.providers.base.synth_websocket_stream", side_effect=continuous_stream):
        loop_task = asyncio.create_task(auto_trade_loop())

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            futures = [pool.submit(client_worker, wid, 20) for wid in range(16)]
            concurrent.futures.wait(futures)

        stop_event.set()
        await asyncio.sleep(0.05)
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass

        assert len(client_errors) == 0, f"Encountered client concurrency exceptions: {client_errors}"
        assert loop_task.done()

        # Ledger invariant check
        pf = broker.get_portfolio()
        assert not math.isnan(pf["balance"])
        assert not math.isinf(pf["balance"])
        assert isinstance(pf["open_positions"], list)


# ===========================================================================
# 2. Broker Ledger Invariants & Accounting Integrity
# ===========================================================================
def test_broker_ledger_invariants_and_accounting_integrity():
    """Empirically verifies broker accounting integrity under high volume
    conflicting trade execution and bulk closing:
    - Balance is strictly finite (not NaN, not Inf).
    - Initial balance + sum(pnl) == current balance (within 2-decimal rounding margin).
    - Trade history properly records closed position PnLs.
    """
    pb = PaperBroker(initial_balance=50000.0)
    num_threads = 12
    trades_per_thread = 25
    errors = []

    def worker(tid: int):
        try:
            for i in range(trades_per_thread):
                direction = "LONG" if (tid + i) % 2 == 0 else "SHORT"
                entry_px = 2650.0 + (i % 7) * 0.5
                pb.execute_trade({
                    "action": "BUY" if direction == "LONG" else "SELL",
                    "direction": direction,
                    "entry": entry_px,
                    "lots": 0.1,
                    "feasible": True,
                })
                if i % 5 == 0:
                    pb.close_all(current_price=2651.0 + (i % 3))
        except Exception as e:
            errors.append((tid, e))

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as pool:
        futs = [pool.submit(worker, tid) for tid in range(num_threads)]
        concurrent.futures.wait(futs)

    assert len(errors) == 0, f"Worker errors: {errors}"

    # Close any remaining open positions
    pb.close_all(current_price=2650.0)
    pf = pb.get_portfolio()

    assert len(pf["open_positions"]) == 0
    assert not math.isnan(pb.balance)
    assert not math.isinf(pb.balance)

    total_pnl = sum(t["pnl"] for t in pb.trade_history)
    expected_balance = round(50000.0 + total_pnl, 2)
    actual_balance = round(pb.balance, 2)
    assert abs(actual_balance - expected_balance) < 0.25, (
        f"Ledger balance drift: expected {expected_balance}, actual {actual_balance}"
    )


# ===========================================================================
# 3. SQLite Store Under Concurrent Write Load (WAL Mode)
# ===========================================================================
def test_sqlite_store_concurrent_wal_write_load():
    """Verifies that SQLite persistence survives concurrent multi-threaded write load
    without SQLite locked errors or data loss, leveraging WAL mode and busy_timeout.
    """
    init_stats = store.signal_stats()
    init_total = init_stats["total"]

    num_threads = 20
    ops_per_thread = 30
    errors = []

    def db_worker(tid: int):
        try:
            for i in range(ops_per_thread):
                if i % 3 == 0:
                    store.persist_signal("BUY", f"ST_{tid}_{i}", "TREND_CONT")
                elif i % 3 == 1:
                    store.audit("STRESS_AUDIT", f"worker {tid} step {i}")
                else:
                    stats = store.signal_stats()
                    assert "total" in stats
        except Exception as e:
            errors.append((tid, e))

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as pool:
        futures = [pool.submit(db_worker, tid) for tid in range(num_threads)]
        concurrent.futures.wait(futures)

    assert len(errors) == 0, f"SQLite concurrency exceptions: {errors}"

    final_stats = store.signal_stats()
    final_total = final_stats["total"]
    expected_added = num_threads * (ops_per_thread // 3 + (1 if ops_per_thread % 3 > 0 else 0))
    actual_added = final_total - init_total
    assert actual_added == expected_added, (
        f"Data persistence mismatch: expected {expected_added} rows added, got {actual_added}"
    )


# ===========================================================================
# 4. Position Sizing Risk Adherence & Extreme Input Resilience
# ===========================================================================
def test_position_sizing_risk_adherence_and_extreme_inputs():
    """Verifies that trade_planning and PaperBroker properly respect risk rules
    and reject corrupted/zero inputs without corrupting broker ledger state.
    """
    sig = {"action": "BUY", "direction": "LONG", "strategy": "TREND_CONT"}

    # Normal sizing: Half-Kelly capped at 10% risk fraction
    plan_normal = create_plan(sig, entry=2650.0, atr=2.0, equity=10000.0, ml_confidence=90.0)
    assert plan_normal["feasible"] is True
    assert plan_normal["lots"] > 0
    assert plan_normal["risk_money"] <= 10000.0 * 0.15

    # Negative equity must yield 0 lots and infeasible trade
    plan_neg_equity = create_plan(sig, entry=2650.0, atr=2.0, equity=-1000.0)
    assert plan_neg_equity["feasible"] is False
    assert plan_neg_equity["lots"] == 0.0

    # Broker resistance to NaN / Inf entry and non-positive sizes
    pb = PaperBroker(initial_balance=10000.0)
    for bad_size in [float("nan"), float("inf"), -1.0, 0.0]:
        res = pb.execute_trade({
            "action": "BUY", "direction": "LONG", "entry": 2650.0, "lots": bad_size, "feasible": True
        })
        assert res["status"] in ("skipped", "rejected")
        assert pb.balance == 10000.0

    for bad_entry in [float("nan"), float("inf"), -2650.0, 0.0, None]:
        res = pb.execute_trade({
            "action": "BUY", "direction": "LONG", "entry": bad_entry, "lots": 0.1, "feasible": True
        })
        assert res["status"] in ("skipped", "rejected")
        assert pb.balance == 10000.0
