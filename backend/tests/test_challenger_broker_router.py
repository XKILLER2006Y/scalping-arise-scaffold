"""Empirical stress test suite for PaperBroker and execution/router.py

Objective 1: Concurrently launch 20+ threads making rapid conflicting calls:
execute_trade (valid and NO_TRADE plans), close_all, and get_portfolio.
Verify thread safety lock prevents state corruption and position counts remain consistent.
Verify NO phantom position is ever opened for malformed, missing, or NO_TRADE plans.

Objective 2: Diverse payloads to POST /api/v1/execution/close_all:
query parameter, empty body, JSON body with extra fields, negative price.
Verify no 422 or 500 unhandled exceptions.
"""
import concurrent.futures
import threading
import time
import pytest
from starlette.testclient import TestClient

from app.execution.engine import PaperBroker, broker
from app.main import app


# ===========================================================================
# 1. PaperBroker Concurrency & State Integrity (24 threads, rapid conflicting calls)
# ===========================================================================
def test_paper_broker_concurrent_stress_and_state_consistency():
    """Stress tests PaperBroker under high concurrent load with 24 threads.
    Validates:
    - Thread safety lock prevents race conditions and data corruption
    - Accurate balance, open position count, and trade history bookkeeping
    - Invariants: balance - initial_balance == sum(closed trade PnLs)
    """
    initial_balance = 100000.0
    stress_broker = PaperBroker(initial_balance=initial_balance)
    
    num_threads = 24
    ops_per_thread = 100  # Total 2400 concurrent operations
    errors = []

    def worker(tid: int):
        try:
            for i in range(ops_per_thread):
                op = (tid * 7 + i) % 5
                if op == 0:
                    # Execute valid BUY
                    res = stress_broker.execute_trade({
                        "action": "BUY",
                        "direction": "LONG",
                        "entry_price": 2600.0 + (i % 10),
                        "stop_loss": 2590.0,
                        "take_profit_1": 2620.0,
                        "position_size": 0.05,
                        "feasible": True,
                    })
                    assert res["status"] in ("filled", "rejected", "skipped")
                elif op == 1:
                    # Execute valid SELL
                    res = stress_broker.execute_trade({
                        "action": "SELL",
                        "direction": "SHORT",
                        "entry": 2610.0 + (i % 10),
                        "stop": 2620.0,
                        "take_profit": 2590.0,
                        "lots": 0.05,
                        "feasible": True,
                    })
                    assert res["status"] in ("filled", "rejected", "skipped")
                elif op == 2:
                    # Execute NO_TRADE or malformed plan
                    res = stress_broker.execute_trade({
                        "action": "NO_TRADE",
                        "feasible": False,
                        "reason": "Stress test NO_TRADE",
                    })
                    assert res["status"] in ("skipped", "rejected")
                elif op == 3:
                    # Close all positions at fluctuating market price
                    px = 2605.0 + (i % 7) - 3.0
                    close_res = stress_broker.close_all(current_price=px)
                    assert "closed" in close_res
                    assert "new_balance" in close_res
                elif op == 4:
                    # Query portfolio
                    pf = stress_broker.get_portfolio()
                    assert "balance" in pf
                    assert "open_positions" in pf
                    assert isinstance(pf["open_positions"], list)
        except Exception as e:
            errors.append((tid, e))

    threads = [threading.Thread(target=worker, args=(tid,)) for tid in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Concurrent execution errors encountered: {errors}"

    # Perform final cleanup to close all remaining positions
    final_close = stress_broker.close_all(current_price=2600.0)
    final_pf = stress_broker.get_portfolio()

    assert len(final_pf["open_positions"]) == 0, (
        f"Expected 0 open positions after final close_all, got: {len(final_pf['open_positions'])}"
    )

    # Invariant verification: Balance integrity
    # Sum of all closed trade pnl must equal (current_balance - initial_balance) within rounding error
    total_trade_pnl = sum(p["pnl"] for p in stress_broker.trade_history)
    expected_balance = round(initial_balance + total_trade_pnl, 2)
    actual_balance = round(stress_broker.balance, 2)
    assert abs(actual_balance - expected_balance) < 0.05, (
        f"Balance corruption detected! Expected {expected_balance}, got {actual_balance}"
    )


# ===========================================================================
# 2. Phantom Position Prevention on Malformed / Missing / NO_TRADE Plans
# ===========================================================================
def test_paper_broker_phantom_trade_exhaustive_prevention():
    """Exhaustively stress tests execute_trade with malformed, missing, and NO_TRADE payloads.
    Verifies NO phantom positions are ever created, and status is strictly skipped or rejected.
    """
    pb = PaperBroker(initial_balance=10000.0)

    adversarial_payloads = [
        None,
        {},
        {"action": "NO_TRADE"},
        {"action": "NO_TRADE", "direction": "LONG", "entry": 2650.0},
        {"action": "NO_TRADE", "direction": "SHORT", "entry_price": 2650.0, "position_size": 1.0},
        {"action": "NO_TRADE", "signal": {"action": "NO_TRADE", "direction": "LONG"}},
        {"signal": {"action": "NO_TRADE"}},
        {"signal": None},
        {"signal": {}},
        {"feasible": False},
        {"feasible": False, "entry": 2650.0, "lots": 0.5, "direction": "LONG"},
        {"feasible": False, "action": "BUY", "direction": "LONG", "entry": 2650.0},
        {"direction": None},
        {"direction": "INVALID_DIRECTION"},
        {"action": "BUY", "direction": "SIDEWAYS"},
        {"action": "SELL"},  # Missing direction and signal
        {"action": "BUY", "direction": "LONG"},  # Missing entry and entry_price
        {"action": "BUY", "direction": "LONG", "entry": None, "entry_price": None},
        {"action": ""},
        {"random_key": "random_value"},
        {"feasible": True, "action": "NO_TRADE", "entry": 2650.0, "direction": "LONG"},
    ]

    for idx, payload in enumerate(adversarial_payloads):
        res = pb.execute_trade(payload)
        assert res["status"] in ("skipped", "rejected"), (
            f"Payload #{idx} ({payload}) did not return skipped/rejected. Got: {res}"
        )
        assert len(pb.open_positions) == 0, (
            f"Phantom trade created by payload #{idx} ({payload})! Positions: {pb.open_positions}"
        )
        assert pb.balance == 10000.0, (
            f"Balance mutated by invalid payload #{idx}! Balance: {pb.balance}"
        )


# ===========================================================================
# 3. Execution Router POST /close_all Payload Diversity Stress Testing
# ===========================================================================
def test_execution_router_close_all_diverse_payloads():
    """Verifies that POST /api/v1/execution/close_all gracefully handles:
    1. Query parameter only (?current_price=2700.5)
    2. Empty body (no body, empty JSON {}, empty raw string)
    3. JSON body with extra unexpected fields
    4. Negative current_price
    5. Both query param and JSON body
    Verifies NO 422 Unprocessable Entity or 500 Internal Server Error occurs.
    """
    client = TestClient(app)

    # Pre-populate a position so close_all actually closes something
    broker.execute_trade({
        "action": "BUY",
        "direction": "LONG",
        "entry": 2600.0,
        "lots": 0.1,
        "feasible": True,
    })

    test_cases = [
        # 1. Query parameter only
        ("Query parameter only", "/api/v1/execution/close_all?current_price=2680.5", {}, None, None),
        # 2. Empty body with no headers
        ("Empty body without Content-Type", "/api/v1/execution/close_all", {}, None, b""),
        # 3. Empty JSON body
        ("Empty JSON body {}", "/api/v1/execution/close_all", {}, {}, None),
        # 4. JSON body with valid price
        ("JSON body valid price", "/api/v1/execution/close_all", {}, {"current_price": 2690.0}, None),
        # 5. JSON body with extra/unexpected fields
        (
            "JSON body with extra fields",
            "/api/v1/execution/close_all",
            {},
            {
                "current_price": 2710.0,
                "extra_field": "unexpected",
                "nested": {"key": 123},
                "symbol": "XAU/USD",
                "random_tags": [1, 2, 3]
            },
            None,
        ),
        # 6. JSON body without current_price (only extra fields)
        (
            "JSON body with only extra fields (fallback default price)",
            "/api/v1/execution/close_all",
            {},
            {"bogus_field": 999, "notes": "no price specified"},
            None,
        ),
        # 7. Negative price via query parameter
        ("Negative price via query param", "/api/v1/execution/close_all?current_price=-150.0", {}, None, None),
        # 8. Negative price via JSON body
        ("Negative price via JSON body", "/api/v1/execution/close_all", {}, {"current_price": -250.0}, None),
        # 9. Conflicting query parameter AND JSON body
        (
            "Conflicting query param and JSON body",
            "/api/v1/execution/close_all?current_price=2600.0",
            {},
            {"current_price": 2700.0},
            None,
        ),
        # 10. null current_price in JSON body
        ("Null current_price in JSON body", "/api/v1/execution/close_all", {}, {"current_price": None}, None),
    ]

    for desc, path, params, json_body, data_content in test_cases:
        # Ensure at least 1 position exists for closing
        broker.execute_trade({
            "action": "BUY",
            "direction": "LONG",
            "entry": 2600.0,
            "lots": 0.05,
            "feasible": True,
        })

        if json_body is not None:
            resp = client.post(path, json=json_body, params=params)
        elif data_content is not None:
            resp = client.post(path, content=data_content, params=params)
        else:
            resp = client.post(path, params=params)

        assert resp.status_code == 200, (
            f"Failed test case '{desc}': Expected 200 OK, got HTTP {resp.status_code}. Response: {resp.text}"
        )
        data = resp.json()
        assert "closed" in data, f"Response missing 'closed' key: {data}"
        assert "new_balance" in data, f"Response missing 'new_balance' key: {data}"


# ===========================================================================
# 4. Concurrent Router Endpoint Stress Testing
# ===========================================================================
def test_execution_router_concurrent_load():
    """Fires 50 concurrent requests against execution router endpoints (/trade, /portfolio, /close_all)
    via Starlette TestClient to ensure no race conditions or deadlock occur at the HTTP layer.
    """
    client = TestClient(app)
    statuses = []

    def make_request(idx: int):
        req_type = idx % 3
        if req_type == 0:
            r = client.post("/api/v1/execution/trade", json={
                "action": "BUY",
                "direction": "LONG",
                "entry": 2650.0,
                "lots": 0.05,
                "feasible": True,
            })
        elif req_type == 1:
            r = client.get("/api/v1/execution/portfolio")
        else:
            r = client.post("/api/v1/execution/close_all", json={"current_price": 2655.0})
        return r.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(make_request, i) for i in range(50)]
        for f in concurrent.futures.as_completed(futures):
            statuses.append(f.result())

    assert all(status == 200 for status in statuses), (
        f"Non-200 responses received during concurrent router load: {set(statuses)}"
    )
