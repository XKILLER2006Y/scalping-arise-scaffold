"""Comprehensive tests for auto_trade_loop coroutine and PaperBroker execution engine.

Covers:
- test_auto_trade_loop_runs_ticks: Processes 3-5 ticks on simulated stream without unhandled errors.
- test_auto_trade_loop_survives_tick_error: Survives transient error on a tick and continues processing.
- test_auto_trade_loop_graceful_cancellation: Clean shutdown on task.cancel() with no orphan tasks.
- test_paper_broker_thread_safety_and_phantom_trade_prevention: NO_TRADE phantom prevention & concurrency.
- Supplementary broker tests: dual schema support, circuit breakers, and PnL calculation.
- test_auto_trade_loop_executes_trade_on_buy_signal: Full BUY pipeline to broker execution.
- test_auto_trade_loop_skips_trade_on_no_trade_signal: Verifies NO_TRADE signals do not execute trades.
"""
import asyncio
import os
import sys
import threading
import time
from unittest.mock import patch, MagicMock

import pytest

# Ensure backend root is in sys.path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.execution.engine import PaperBroker, broker
from app.market_data.models import Candle, SourceType
from app.main import auto_trade_loop, app


def _make_candle(i: int, base_price: float = 2650.0) -> Candle:
    price = base_price + ((i * 37) % 11 - 5) * 0.35
    o = price
    c = price + 0.2
    h = max(o, c) + 0.5
    l = min(o, c) - 0.5
    return Candle(
        timestamp=int(time.time()) + i * 60,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=1000 + i * 50,
        provider_instrument="XAU/USD",
        source="twelve_data",
        source_type=SourceType.SPOT,
    )


async def _fast_synth_stream(num_ticks: int = 5, delay: float = 0.02):
    """Synthetic stream emitting num_ticks with minimal latency for fast, deterministic testing."""
    for i in range(num_ticks):
        yield _make_candle(i)
        if delay > 0:
            await asyncio.sleep(delay)


async def _infinite_synth_stream(delay: float = 0.02):
    """Infinite synthetic stream for cancellation testing."""
    i = 0
    while True:
        yield _make_candle(i)
        i += 1
        await asyncio.sleep(delay)


# ---------------------------------------------------------------------------
# Task 1: test_auto_trade_loop_runs_ticks
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_auto_trade_loop_runs_ticks():
    """Runs auto_trade_loop() for 3-5 ticks with a simulated/synthetic stream
    without throwing any unhandled exceptions.
    """
    ticks_processed = 0

    from app.strategy import engine as strat_engine
    real_evaluate_all = strat_engine.evaluate_all

    def spy_evaluate_all(*args, **kwargs):
        nonlocal ticks_processed
        ticks_processed += 1
        return real_evaluate_all(*args, **kwargs)

    with patch("app.market_data.providers.base.synth_websocket_stream", side_effect=lambda *a, **kw: _fast_synth_stream(5, 0.03)), \
         patch("app.strategy.engine.evaluate_all", side_effect=spy_evaluate_all):

        task = asyncio.create_task(auto_trade_loop())

        # Wait for at least 3-5 ticks to be processed or timeout
        for _ in range(50):
            if ticks_processed >= 4:
                break
            await asyncio.sleep(0.05)

        # Allow final execution to settle
        await asyncio.sleep(0.05)

        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Verification: No unhandled exceptions occurred
        exc = task.exception() if not task.cancelled() else None
        assert exc is None, f"auto_trade_loop raised an unhandled exception: {exc}"
        assert ticks_processed >= 3, (
            f"Expected at least 3 ticks to be processed, but only processed {ticks_processed}"
        )


# ---------------------------------------------------------------------------
# Task 2: test_auto_trade_loop_survives_tick_error
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_auto_trade_loop_survives_tick_error():
    """Mocks or injects a temporary exception during one tick (e.g., market data
    hiccup or pricing error) and verifies that auto_trade_loop() catches and
    logs the error, and continues running on subsequent ticks rather than dying.
    """
    call_log = []

    from app.technical_features import engine as feat_engine
    real_compute_features = feat_engine.compute_features

    def flaky_compute_features(*args, **kwargs):
        call_idx = len(call_log) + 1
        call_log.append(call_idx)
        if call_idx == 2:
            # Simulate a temporary pricing/market data hiccup on tick 2
            raise ValueError("Simulated market data calculation hiccup on tick 2")
        return real_compute_features(*args, **kwargs)

    with patch("app.market_data.providers.base.synth_websocket_stream", side_effect=lambda *a, **kw: _fast_synth_stream(5, 0.03)), \
         patch("app.technical_features.engine.compute_features", side_effect=flaky_compute_features):

        task = asyncio.create_task(auto_trade_loop())

        # Wait for subsequent ticks after tick 2
        for _ in range(50):
            if len(call_log) >= 4:
                break
            await asyncio.sleep(0.05)

        await asyncio.sleep(0.05)

        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Verification:
        # 1. Tick 2 raised an error, but the loop must have survived and called subsequent ticks (tick 3+)
        assert len(call_log) >= 3, (
            f"Loop failed to survive tick error: stopped at call count {len(call_log)}, calls: {call_log}"
        )
        # 2. No unhandled exception killed the task prematurely
        exc = task.exception() if not task.cancelled() else None
        assert exc is None, f"Task terminated with unhandled exception: {exc}"


# ---------------------------------------------------------------------------
# Task 3: test_auto_trade_loop_graceful_cancellation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_auto_trade_loop_graceful_cancellation():
    """Launches auto_trade_loop() as an asyncio.create_task, cancels it via
    task.cancel(), and verifies that it shuts down cleanly with CancelledError
    handled and no orphan background tasks.
    """
    with patch("app.market_data.providers.base.synth_websocket_stream", side_effect=lambda *a, **kw: _infinite_synth_stream(0.02)):
        current = asyncio.current_task()
        tasks_before = {t for t in asyncio.all_tasks() if t is not current}

        task = asyncio.create_task(auto_trade_loop())

        # Let it run briefly
        await asyncio.sleep(0.1)
        assert not task.done(), "auto_trade_loop finished prematurely before cancellation"

        # Cancel the task
        task.cancel()

        # Await task cancellation
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except asyncio.CancelledError:
            pass

        # Verify task is done and shutdown was clean
        assert task.done() is True, "Task was not completed after cancellation"
        exc = task.exception() if not task.cancelled() else None
        assert exc is None, f"Task threw an unexpected exception during cancellation: {exc}"

        # Verify no orphan background tasks leaked
        tasks_after = {t for t in asyncio.all_tasks() if t is not current and not t.done()}
        assert task not in tasks_after, "Cancelled task is still present in active tasks"
        orphan_tasks = tasks_after - tasks_before
        assert len(orphan_tasks) == 0, f"Found leaked orphan background tasks: {orphan_tasks}"


# ---------------------------------------------------------------------------
# Task 4: test_paper_broker_thread_safety_and_phantom_trade_prevention
# ---------------------------------------------------------------------------
def test_paper_broker_thread_safety_and_phantom_trade_prevention():
    """Verifies that calling broker.execute_trade with a NO_TRADE plan returns
    skipped and DOES NOT create a phantom position, and tests concurrent execution
    from multiple threads.
    """
    test_broker = PaperBroker(initial_balance=10000.0)

    # 1. Verify NO_TRADE & Infeasible Plans DO NOT create phantom positions
    no_trade_payloads = [
        {"action": "NO_TRADE"},
        {"action": "NO_TRADE", "signal": {"action": "NO_TRADE"}},
        {"feasible": False, "reason": "no trade or ATR unavailable", "signal": {"action": "NO_TRADE"}},
        {"feasible": False, "entry": 2650.0, "lots": 0.1},
        {"feasible": False, "entry_price": 2650.0, "position_size": 0.1},
        {},
        None,
        {"signal": {"action": "NO_TRADE"}},
        {"action": "NO_TRADE", "entry_price": 2650.0, "direction": "LONG"},
        {"feasible": True, "action": "NO_TRADE", "direction": None},
    ]

    for payload in no_trade_payloads:
        res = test_broker.execute_trade(payload)
        assert res["status"] in ("skipped", "rejected"), (
            f"Expected skipped or rejected status for payload {payload}, got: {res}"
        )
        assert len(test_broker.open_positions) == 0, (
            f"Phantom trade created! open_positions should be empty for payload {payload}, but got: {test_broker.open_positions}"
        )

    # 2. Verify Valid Trade DOES execute properly (legacy and plan formats)
    valid_legacy = {
        "action": "BUY",
        "direction": "LONG",
        "entry_price": 2650.0,
        "stop_loss": 2640.0,
        "take_profit_1": 2670.0,
        "position_size": 0.1,
        "feasible": True,
    }
    res_legacy = test_broker.execute_trade(valid_legacy)
    assert res_legacy["status"] == "filled"
    assert len(test_broker.open_positions) == 1
    assert test_broker.open_positions[0]["direction"] == "LONG"
    assert test_broker.open_positions[0]["entry"] == 2650.0

    valid_plan = {
        "action": "SELL",
        "direction": "SHORT",
        "entry": 2655.0,
        "stop": 2665.0,
        "take_profit": 2635.0,
        "lots": 0.2,
        "feasible": True,
    }
    res_plan = test_broker.execute_trade(valid_plan)
    assert res_plan["status"] == "filled"
    assert len(test_broker.open_positions) == 2

    # Clean up positions before concurrency test
    test_broker.close_all(2652.0)
    assert len(test_broker.open_positions) == 0

    # 3. Verify Thread Safety & Concurrent Execution from multiple threads
    assert hasattr(test_broker, "_lock"), "PaperBroker missing _lock attribute"
    assert isinstance(test_broker._lock, (threading.Lock, type(threading.Lock()))), (
        "PaperBroker._lock must be a threading.Lock instance"
    )

    concurrent_broker = PaperBroker(initial_balance=10000.0)
    exceptions = []
    num_threads = 12
    iterations_per_thread = 40

    def worker(tid: int):
        try:
            for i in range(iterations_per_thread):
                op = (tid + i) % 4
                if op == 0:
                    # Infeasible / NO_TRADE
                    r = concurrent_broker.execute_trade({"action": "NO_TRADE", "feasible": False})
                    assert r["status"] in ("skipped", "rejected")
                elif op == 1:
                    # Valid BUY
                    r = concurrent_broker.execute_trade({
                        "action": "BUY",
                        "direction": "LONG",
                        "entry": 2650.0 + (i % 5),
                        "stop": 2640.0,
                        "take_profit": 2670.0,
                        "lots": 0.05,
                        "feasible": True,
                    })
                    assert r["status"] in ("filled", "rejected")
                elif op == 2:
                    # Read portfolio
                    port = concurrent_broker.get_portfolio()
                    assert "balance" in port
                    assert "open_positions" in port
                else:
                    # Close all positions
                    concurrent_broker.close_all(current_price=2651.0)
        except Exception as exc:
            exceptions.append((tid, exc))

    threads = [threading.Thread(target=worker, args=(tid,)) for tid in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(exceptions) == 0, f"Thread safety violated! Exceptions occurred: {exceptions}"


# ---------------------------------------------------------------------------
# Supplementary Tests: Circuit Breaker, Close All PnL, Signal Execution
# ---------------------------------------------------------------------------
def test_paper_broker_circuit_breakers():
    """Verifies that trailing drawdown (8%) and daily loss (4%) circuit breakers
    halt the broker and reject trades.
    """
    # 1. Trailing Drawdown Limit: 8%
    broker_dd = PaperBroker(initial_balance=10000.0)
    broker_dd.balance = 9100.0  # 9% drawdown from 10000 high water mark
    res_dd = broker_dd.execute_trade({
        "action": "BUY",
        "direction": "LONG",
        "entry": 2650.0,
        "feasible": True,
    })
    assert res_dd["status"] == "rejected"
    assert "Circuit Breaker" in res_dd["reason"]
    assert broker_dd.is_halted is True

    # 2. Daily Loss Limit: 4%
    broker_dl = PaperBroker(initial_balance=10000.0)
    broker_dl.balance = 9550.0  # 4.5% loss from 10000 daily start balance
    res_dl = broker_dl.execute_trade({
        "action": "BUY",
        "direction": "LONG",
        "entry": 2650.0,
        "feasible": True,
    })
    assert res_dl["status"] == "rejected"
    assert "Daily Loss Limit" in res_dl["reason"]
    assert broker_dl.is_halted is True


def test_paper_broker_close_all_pnl_calculation():
    """Verifies close_all correctly calculates PnL for LONG and SHORT positions."""
    broker_pnl = PaperBroker(initial_balance=10000.0)

    # Open LONG: entry 2650.0, size 0.1
    broker_pnl.execute_trade({
        "action": "BUY", "direction": "LONG", "entry": 2650.0, "lots": 0.1, "feasible": True
    })
    # Open SHORT: entry 2660.0, size 0.2
    broker_pnl.execute_trade({
        "action": "SELL", "direction": "SHORT", "entry": 2660.0, "lots": 0.2, "feasible": True
    })

    assert len(broker_pnl.open_positions) == 2

    # Close all at 2655.0 (contract_oz = 100):
    # LONG PnL: (2655.0 - 2650.0) * 0.1 * 100 = +50.00
    # SHORT PnL: (2660.0 - 2655.0) * 0.2 * 100 = +100.00
    # Total PnL: +150.00
    res = broker_pnl.close_all(current_price=2655.0)
    assert len(res["closed"]) == 2
    assert len(broker_pnl.open_positions) == 0
    assert broker_pnl.balance == 10150.0
    assert len(broker_pnl.trade_history) == 2


@pytest.mark.asyncio
async def test_auto_trade_loop_executes_trade_on_buy_signal():
    """Verifies that when a qualified BUY signal is generated, auto_trade_loop
    generates a feasible plan and calls broker.execute_trade with valid order.
    """
    mock_signal = {
        "action": "BUY",
        "direction": "LONG",
        "rule": "TREND_CONT",
        "confidence": 0.88,
        "timestamp": int(time.time()),
    }

    trades_executed = []
    original_execute_trade = broker.execute_trade

    def spy_execute_trade(plan):
        trades_executed.append(plan)
        return original_execute_trade(plan)

    with patch("app.market_data.providers.base.synth_websocket_stream", side_effect=lambda *a, **kw: _fast_synth_stream(3, 0.02)), \
         patch("app.signals.engine.decide", return_value=mock_signal), \
         patch.object(broker, "execute_trade", side_effect=spy_execute_trade):

        task = asyncio.create_task(auto_trade_loop())

        for _ in range(30):
            if len(trades_executed) >= 1:
                break
            await asyncio.sleep(0.05)

        await asyncio.sleep(0.05)

        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert len(trades_executed) >= 1, "Expected at least 1 trade execution for BUY signal"
        trade = trades_executed[0]
        assert trade.get("action") == "BUY" or trade.get("signal", {}).get("action") == "BUY"
        assert trade.get("direction") == "LONG" or trade.get("signal", {}).get("direction") == "LONG"


@pytest.mark.asyncio
async def test_auto_trade_loop_skips_trade_on_no_trade_signal():
    """Verifies that when a NO_TRADE signal is generated, auto_trade_loop
    does not execute an open order with the broker.
    """
    mock_no_trade_signal = {
        "action": "NO_TRADE",
        "direction": None,
        "rule": "NO_RULE",
        "confidence": 0.0,
        "timestamp": int(time.time()),
    }

    executed_trades = []
    original_execute_trade = broker.execute_trade

    def spy_execute_trade(plan):
        executed_trades.append(plan)
        return original_execute_trade(plan)

    initial_position_count = len(broker.open_positions)

    with patch("app.market_data.providers.base.synth_websocket_stream", side_effect=lambda *a, **kw: _fast_synth_stream(3, 0.02)), \
         patch("app.signals.engine.decide", return_value=mock_no_trade_signal), \
         patch.object(broker, "execute_trade", side_effect=spy_execute_trade):

        task = asyncio.create_task(auto_trade_loop())

        await asyncio.sleep(0.2)

        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Verify either execute_trade was never called or no positions were added
        assert len(broker.open_positions) == initial_position_count, (
            "NO_TRADE signal should not result in new open positions"
        )
