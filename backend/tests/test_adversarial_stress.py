"""Adversarial stress-testing harnesses for Scalping Arise backend.

Empirically tests:
1. auto_trade_loop resilience under extreme tick values (NaN, Inf, negative prices, zero volume).
2. auto_trade_loop resilience under exception storms and transient errors.
3. auto_trade_loop stream generator network drop and reconnect dynamics.
4. auto_trade_loop rapid task creation, cancellation, and restart cycles (deadlock/orphan prevention).
5. market_data/service.py multi-threaded concurrency, cache poisoning prevention, and chronological slicing.
6. intelligence/sentiment.py zero/single/warmup candle arrays with None indicator values (zero TypeErrors).
"""

import asyncio
import math
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, MagicMock
import numpy as np

import pytest

# Ensure backend root is in sys.path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.execution.engine import PaperBroker, broker
from app.market_data.models import Candle, SourceType
from app.market_data.service import get_candles, _cache
from app.technical_features.engine import compute_features
from app.market_analysis.engine import analyze_market, analyze
from app.intelligence.sentiment import analyze_sentiment
from app.main import auto_trade_loop


# Helper to build valid base candle
def _make_base_candle(i: int, base_price: float = 2650.0) -> Candle:
    o = base_price + (i % 5) * 0.1
    c = o + 0.2
    h = c + 0.5
    l = o - 0.5
    return Candle(
        timestamp=int(time.time()) + i * 60,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=1000.0 + i * 10,
        provider_instrument="XAU/USD",
        source="twelve_data",
        source_type=SourceType.SPOT,
    )


# ===========================================================================
# 1. auto_trade_loop Extreme Tick Values
# ===========================================================================
@pytest.mark.asyncio
async def test_auto_trade_loop_extreme_tick_values():
    """Injects extreme ticks (NaN, Inf, negative prices, zero volume) interleaved
    with valid ticks and verifies auto_trade_loop never crashes or terminates prematurely.
    """
    extreme_ticks = [
        # 0: Normal valid tick
        _make_base_candle(0, 2650.0),
        # 1: Zero volume
        Candle(
            timestamp=int(time.time()) + 60,
            open=2651.0, high=2652.0, low=2650.0, close=2651.5, volume=0.0,
            provider_instrument="XAU/USD", source="twelve_data", source_type=SourceType.SPOT,
        ),
        # 2: Negative prices
        Candle(
            timestamp=int(time.time()) + 120,
            open=-2650.0, high=-2600.0, low=-2700.0, close=-2640.0, volume=100.0,
            provider_instrument="XAU/USD", source="twelve_data", source_type=SourceType.SPOT,
        ),
        # 3: NaN values
        Candle(
            timestamp=int(time.time()) + 180,
            open=float("nan"), high=float("nan"), low=float("nan"), close=float("nan"), volume=float("nan"),
            provider_instrument="XAU/USD", source="twelve_data", source_type=SourceType.SPOT,
        ),
        # 4: Positive Infinity
        Candle(
            timestamp=int(time.time()) + 240,
            open=float("inf"), high=float("inf"), low=float("inf"), close=float("inf"), volume=1000.0,
            provider_instrument="XAU/USD", source="twelve_data", source_type=SourceType.SPOT,
        ),
        # 5: Negative Infinity
        Candle(
            timestamp=int(time.time()) + 300,
            open=-float("inf"), high=-float("inf"), low=-float("inf"), close=-float("inf"), volume=1000.0,
            provider_instrument="XAU/USD", source="twelve_data", source_type=SourceType.SPOT,
        ),
        # 6: Recovery normal tick
        _make_base_candle(6, 2655.0),
        # 7: Another recovery normal tick
        _make_base_candle(7, 2656.0),
    ]

    ticks_yielded = 0
    ticks_processed = 0

    async def extreme_stream(*args, **kwargs):
        nonlocal ticks_yielded
        for t in extreme_ticks:
            ticks_yielded += 1
            yield t
            await asyncio.sleep(0.02)

    # Monitor ticks passing through the loop pipeline
    from app.strategy import engine as strat_engine
    orig_evaluate_all = strat_engine.evaluate_all

    def track_evaluate_all(*args, **kwargs):
        nonlocal ticks_processed
        ticks_processed += 1
        return orig_evaluate_all(*args, **kwargs)

    with patch("app.market_data.providers.base.synth_websocket_stream", side_effect=extreme_stream), \
         patch("app.strategy.engine.evaluate_all", side_effect=track_evaluate_all):

        task = asyncio.create_task(auto_trade_loop())

        # Wait until all 8 ticks are emitted and processed
        for _ in range(100):
            if ticks_yielded >= len(extreme_ticks) and task.done():
                break
            await asyncio.sleep(0.05)

        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Loop must survive all ticks without dying from unhandled exception
        assert not task.cancelled() or task.done()
        if not task.cancelled() and task.done():
            exc = task.exception()
            assert exc is None, f"Loop raised unhandled exception on extreme tick: {exc}"

        assert ticks_yielded == 8, f"Expected 8 ticks yielded, got {ticks_yielded}"
        # Ticks may raise in math calculations (e.g. NaN/Inf in indicators),
        # but the per-tick try-except MUST catch and continue so the remaining ticks process!
        assert ticks_processed >= 2, f"Expected at least the normal recovery ticks to reach evaluate_all, got {ticks_processed}"


# ===========================================================================
# 2. auto_trade_loop Exception Storms in Tick Processing
# ===========================================================================
@pytest.mark.asyncio
async def test_auto_trade_loop_exception_storms():
    """Simulates an exception storm during tick processing (multiple different
    exceptions on consecutive ticks) and verifies auto_trade_loop survives
    every failure and continues running.
    """
    total_ticks = 10
    exceptions_thrown = 0
    clean_ticks_processed = 0

    async def tick_stream(*args, **kwargs):
        for i in range(total_ticks):
            yield _make_base_candle(i, 2650.0 + i)
            await asyncio.sleep(0.02)

    from app.technical_features import engine as feat_engine
    orig_compute_features = feat_engine.compute_features

    def storm_compute_features(history, symbol="XAU/USD"):
        nonlocal exceptions_thrown, clean_ticks_processed
        idx = exceptions_thrown + clean_ticks_processed
        if idx == 1:
            exceptions_thrown += 1
            raise ValueError("Storm 1: Corrupted feature array")
        elif idx == 2:
            exceptions_thrown += 1
            raise KeyError("Storm 2: Missing indicator key")
        elif idx == 3:
            exceptions_thrown += 1
            raise ZeroDivisionError("Storm 3: Division by zero in ATR")
        elif idx == 4:
            exceptions_thrown += 1
            raise RuntimeError("Storm 4: Internal provider timeout")
        else:
            clean_ticks_processed += 1
            return orig_compute_features(history, symbol)

    with patch("app.market_data.providers.base.synth_websocket_stream", side_effect=tick_stream), \
         patch("app.technical_features.engine.compute_features", side_effect=storm_compute_features):

        task = asyncio.create_task(auto_trade_loop())

        # Wait for all ticks to pass through
        for _ in range(100):
            if (exceptions_thrown + clean_ticks_processed) >= total_ticks:
                break
            await asyncio.sleep(0.05)

        await asyncio.sleep(0.05)

        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert exceptions_thrown == 4, f"Expected 4 exceptions in storm, got {exceptions_thrown}"
        assert clean_ticks_processed == 6, f"Expected 6 clean ticks processed, got {clean_ticks_processed}"
        assert task.cancelled() or task.exception() is None


# ===========================================================================
# 3. auto_trade_loop Stream Generator Network Drops & Reconnects
# ===========================================================================
@pytest.mark.asyncio
async def test_auto_trade_loop_stream_generator_reconnect_drops():
    """Simulates a stream generator experiencing intermittent network drops,
    stalls, and internal reconnects, verifying auto_trade_loop gracefully
    receives ticks across disconnect/reconnect intervals.
    """
    ticks_emitted = 0

    async def reconnecting_stream(*args, **kwargs):
        nonlocal ticks_emitted
        for i in range(8):
            if i in (2, 5):
                # Simulate network socket drop / reconnection latency
                await asyncio.sleep(0.1)
            ticks_emitted += 1
            yield _make_base_candle(i, 2650.0 + i)
            await asyncio.sleep(0.02)

    processed_count = 0
    from app.strategy import engine as strat_engine
    orig_eval = strat_engine.evaluate_all

    def spy_eval(*args, **kwargs):
        nonlocal processed_count
        processed_count += 1
        return orig_eval(*args, **kwargs)

    with patch("app.market_data.providers.base.synth_websocket_stream", side_effect=reconnecting_stream), \
         patch("app.strategy.engine.evaluate_all", side_effect=spy_eval):

        task = asyncio.create_task(auto_trade_loop())

        for _ in range(80):
            if processed_count >= 8:
                break
            await asyncio.sleep(0.05)

        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert ticks_emitted == 8, f"Expected 8 emitted, got {ticks_emitted}"
        assert processed_count == 8, f"Expected 8 processed across drops, got {processed_count}"


# ===========================================================================
# 4. auto_trade_loop Rapid Task Churn (Deadlock & Orphan Prevention)
# ===========================================================================
@pytest.mark.asyncio
async def test_auto_trade_loop_rapid_task_churn():
    """Executes 50 rapid cycles of creating, running briefly, cancelling,
    and awaiting auto_trade_loop tasks. Ensures:
    1. Zero deadlocks or hangs.
    2. Zero unhandled exceptions.
    3. No orphaned coroutines or lingering tasks.
    """
    num_cycles = 50

    async def infinite_test_stream(*args, **kwargs):
        idx = 0
        while True:
            yield _make_base_candle(idx)
            idx += 1
            await asyncio.sleep(0.005)

    with patch("app.market_data.providers.base.synth_websocket_stream", side_effect=infinite_test_stream):
        initial_tasks = {t for t in asyncio.all_tasks() if not t.done()}

        for cycle in range(num_cycles):
            t = asyncio.create_task(auto_trade_loop())
            # Let it spin up and potentially process prefetch/first tick
            await asyncio.sleep(0.003)
            # Cancel immediately
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
            assert t.done(), f"Task in cycle {cycle} failed to terminate after cancel()"
            assert t.cancelled() or t.exception() is None

        # Give event loop a microsecond to clean up any references
        await asyncio.sleep(0.05)

        remaining_tasks = {t for t in asyncio.all_tasks() if not t.done()}
        new_tasks = remaining_tasks - initial_tasks
        # Exclude the current test task
        new_tasks = {t for t in new_tasks if t != asyncio.current_task()}

        assert len(new_tasks) == 0, f"Found orphaned tasks after rapid churn: {new_tasks}"


# ===========================================================================
# 5. market_data/service.py Multi-Threaded Concurrency & Slicing
# ===========================================================================
def test_market_data_cache_poisoning_and_slicing_multithreaded():
    """Rapidly interleaves get_candles(limit=1) and get_candles(limit=250) across
    20 concurrent worker threads (100 calls each).

    Adversarial verification:
    1. get_candles(limit=1) NEVER poisons the cache into returning <=1 candle for limit=250.
    2. Every limit=1 call returns exactly 1 candle.
    3. Every limit=250 call returns exactly 250 candles.
    4. Slicing is strictly chronological ([-limit:]) with timestamps monotonically non-decreasing.
    5. The single candle for limit=1 has a timestamp matching the newest candle of limit=250.
    """
    _cache.clear()

    # Prefill cache once so all threads hit cached or refreshed data
    candles_250, meta_250 = get_candles("XAU/USD", "1m", limit=250)
    assert len(candles_250) == 250, f"Initial fetch should return 250 candles, got {len(candles_250)}"

    num_threads = 20
    calls_per_thread = 50
    results_limit_1 = []
    results_limit_250 = []
    errors = []
    lock = threading.Lock()

    def worker(worker_id: int):
        for i in range(calls_per_thread):
            try:
                # Rapidly alternate or pick limit
                if (worker_id + i) % 2 == 0:
                    c1, m1 = get_candles("XAU/USD", "1m", limit=1)
                    with lock:
                        results_limit_1.append((c1, m1))
                else:
                    c250, m250 = get_candles("XAU/USD", "1m", limit=250)
                    with lock:
                        results_limit_250.append((c250, m250))
            except Exception as e:
                with lock:
                    errors.append(f"Worker {worker_id} call {i} error: {e}")

    threads = [threading.Thread(target=worker, args=(wid,)) for wid in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert len(errors) == 0, f"Encountered concurrency errors: {errors}"
    assert len(results_limit_1) > 0, "No limit=1 results recorded"
    assert len(results_limit_250) > 0, "No limit=250 results recorded"

    # Verify limit=1 invariant
    for c, meta in results_limit_1:
        assert len(c) == 1, f"Cache poisoning! limit=1 returned {len(c)} candles (expected 1)"

    # Verify limit=250 invariant
    for c, meta in results_limit_250:
        assert len(c) == 250, (
            f"Cache poisoning! limit=250 returned {len(c)} candles! "
            f"Cache was truncated by a limit=1 call."
        )
        # Verify strictly chronological ordering
        for idx in range(len(c) - 1):
            assert c[idx].timestamp <= c[idx + 1].timestamp, (
                f"Slicing error! Inverted chronological order at index {idx}: "
                f"{c[idx].timestamp} > {c[idx+1].timestamp}"
            )

    # Cross-verify chronological alignment between limit=1 and limit=250
    sample_c1 = results_limit_1[-1][0][0]
    sample_c250_last = results_limit_250[-1][0][-1]
    assert sample_c1.timestamp == sample_c250_last.timestamp, (
        f"limit=1 timestamp {sample_c1.timestamp} does not match limit=250 tail {sample_c250_last.timestamp}"
    )


# ===========================================================================
# 6. intelligence/sentiment.py Indicator Warmup Periods (Zero TypeErrors)
# ===========================================================================
def test_sentiment_indicator_warmup_none_and_edge_cases():
    """Passes candle arrays with 0 candles, 1 candle, 10 candles (warmup periods
    where all indicator values are None) and adversarial feature dictionaries to
    ensure zero TypeErrors or unhandled crashes occur.
    """
    test_candle_counts = [0, 1, 5, 10, 14, 20, 50, 199]

    for count in test_candle_counts:
        candles = [_make_base_candle(i) for i in range(count)]

        # 1. Compute features during warmup
        feats = compute_features(candles, symbol="XAU/USD")
        feat_dict = dict(feats["features"])
        feat_dict["_volatility"] = feats.get("volatility")
        feat_dict["volatility"] = feats.get("volatility")

        # 2. Compute market analysis
        analysis = analyze_market(candles) if count > 0 else {}
        analysis_dict = analysis.model_dump() if hasattr(analysis, "model_dump") else analysis

        # 3. Analyze sentiment - MUST NOT RAISE TypeError
        sentiment = analyze_sentiment(feat_dict, analysis_dict)

        assert isinstance(sentiment, dict), f"Expected dict from analyze_sentiment for {count} candles"
        assert "sentiment" in sentiment, f"Missing sentiment key for {count} candles"
        assert "confidence" in sentiment, f"Missing confidence key for {count} candles"
        assert 0 <= sentiment["confidence"] <= 100, f"Confidence out of bounds: {sentiment['confidence']}"

    # Explicit adversarial input tests with None, NaN, and missing structures
    adversarial_payloads = [
        # All indicator values explicitly None
        ({"ema20": None, "ema50": None, "ema200": None, "rsi14": None, "atr14": None}, {}),
        # Empty features dictionary
        ({}, {}),
        # None as structure
        ({"ema20": 2650.0, "ema200": 2640.0, "rsi14": 55.0}, None),
        # Structure as list instead of dict
        ({"ema20": 2650.0, "ema200": 2640.0, "rsi14": 55.0}, []),
        # Extreme oversold RSI = 0.0
        ({"ema20": 2640.0, "ema200": 2650.0, "rsi14": 0.0}, {"trend": "DOWNTREND"}),
        # Extreme overbought RSI = 100.0
        ({"ema20": 2660.0, "ema200": 2650.0, "rsi14": 100.0}, {"trend": "UPTREND"}),
        # Inf and -Inf values
        ({"ema20": float("inf"), "ema200": -float("inf"), "rsi14": 50.0}, {"trend": "RANGE"}),
    ]

    for f_dict, struct in adversarial_payloads:
        res = analyze_sentiment(f_dict, struct)
        assert isinstance(res, dict)
        assert res["sentiment"] in ("BULLISH", "BEARISH", "NEUTRAL")
        assert 0 <= res["confidence"] <= 100


# ===========================================================================
# 7. ML Pipeline Missing Model & Corrupted Pickle Recovery
# ===========================================================================
def test_ml_pipeline_missing_model_and_corrupted_pickle(tmp_path):
    """Verifies analyze_sentiment and XGBoostSentimentModel handle missing,
    0-byte, and corrupted pickle files gracefully without unhandled exceptions.
    """
    sample_features = {
        "1m": {
            "features": {
                "return": 0.001, "log_return": 0.001, "volatility_14": 0.002,
                "gk_vol": 0.002, "buy_pressure": 0.55, "cvd": 120.0,
                "rsi14": 54.0, "dist_sma9": 0.0005, "dist_sma21": 0.001, "volume": 1500.0
            }
        }
    }
    structure = {"trend": "UPTREND"}

    # Case A: Model path does not exist
    with patch("os.path.exists", return_value=False):
        res = analyze_sentiment(sample_features, structure)
        assert res["sentiment"] in ("BULLISH", "BEARISH", "NEUTRAL")
        assert 0 <= res["confidence"] <= 100

    # Case B: Corrupted 0-byte pickle file
    empty_pkl = tmp_path / "empty_model.pkl"
    empty_pkl.write_bytes(b"")
    with patch("os.path.exists", return_value=True), patch("joblib.load", side_effect=EOFError("Unexpected EOF")):
        res = analyze_sentiment(sample_features, structure)
        assert res["sentiment"] in ("BULLISH", "BEARISH", "NEUTRAL")
        assert 0 <= res["confidence"] <= 100

    # Case C: Random garbage bytes / invalid pickle header
    corrupt_pkl = tmp_path / "corrupt_model.pkl"
    corrupt_pkl.write_bytes(b"CORRUPT_HEADER_GARBAGE_BYTES_12345")
    with patch("os.path.exists", return_value=True), patch("joblib.load", side_effect=Exception("Invalid pickle header")):
        res = analyze_sentiment(sample_features, structure)
        assert isinstance(res, dict)
        assert res["sentiment"] in ("BULLISH", "BEARISH", "NEUTRAL")
        assert 0 <= res["confidence"] <= 100

    # Case D: XGBoostSentimentModel handling corrupted file directly
    from app.intelligence.ml_model import XGBoostSentimentModel
    with patch("app.intelligence.ml_model.MODEL_PATH", str(corrupt_pkl)):
        m = XGBoostSentimentModel()
        pred = m.predict({"ema20": 2650.0, "rsi14": 55.0})
        assert pred["sentiment"] == "NEUTRAL"
        assert pred["confidence"] == 0


# ===========================================================================
# 8. ML Pipeline Extreme Features & NaN/Inf Probability Handling
# ===========================================================================
def test_ml_pipeline_extreme_features_and_nan_probabilities():
    """Verifies analyze_sentiment survives NaN/Inf probabilities and extreme
    numeric inputs without raising ValueError or OverflowError.
    """
    mock_model = MagicMock()

    # Subcase A: Model returns NaN probability
    mock_model.predict_proba.return_value = np.array([[0.0, float("nan")]])
    with patch("os.path.exists", return_value=True), patch("joblib.load", return_value=mock_model):
        res = analyze_sentiment({"1m": {"features": {"return": 0.01}}}, {})
        assert isinstance(res, dict)
        assert not math.isnan(res["confidence"])
        assert 0 <= res["confidence"] <= 100

    # Subcase B: Model returns Inf probability
    mock_model.predict_proba.return_value = np.array([[0.0, float("inf")]])
    with patch("os.path.exists", return_value=True), patch("joblib.load", return_value=mock_model):
        res = analyze_sentiment({"1m": {"features": {"return": 0.01}}}, {})
        assert isinstance(res, dict)
        assert not math.isinf(res["confidence"])
        assert 0 <= res["confidence"] <= 100

    # Subcase C: Extreme feature inputs (Inf, -Inf, 1e300, negative price range, CVD Inf, negative volume)
    extreme_feat_dict = {
        "1m": {
            "features": {
                "return": float("inf"),
                "log_return": -float("inf"),
                "volatility_14": 1e300,
                "gk_vol": float("nan"),
                "price_range": -10.0,
                "cvd": float("inf"),
                "rsi14": float("nan"),
                "volume": -500.0,
            }
        }
    }
    res_extreme = analyze_sentiment(extreme_feat_dict, {"trend": "RANGE"})
    assert isinstance(res_extreme, dict)
    assert res_extreme["sentiment"] in ("BULLISH", "BEARISH", "NEUTRAL")
    assert 0 <= res_extreme["confidence"] <= 100


# ===========================================================================
# 9. ML Pipeline Kelly Sizing & Broker Immunity Under Anomalies
# ===========================================================================
def test_ml_pipeline_kelly_sizing_and_broker_immunity_under_anomalies():
    """Verifies create_plan and PaperBroker cleanly handle aberrant ML confidence
    values without generating corrupted sizing or corrupting broker ledger balance.
    """
    from app.trade_planning.engine import create_plan
    pb = PaperBroker(initial_balance=10000.0)
    sig = {"action": "BUY", "direction": "LONG", "strategy": "TREND_CONT"}

    adversarial_confs = [
        float("nan"), float("inf"), -float("inf"), -50.0, 150.0, 0.0, 100.0, None, "invalid"
    ]

    for conf in adversarial_confs:
        plan = create_plan(sig, entry=2650.0, atr=2.5, equity=10000.0, ml_confidence=conf)
        assert isinstance(plan, dict)
        assert not math.isnan(plan["lots"])
        assert not math.isinf(plan["lots"])
        assert plan["lots"] >= 0.0
        # Position sizing must never exceed maximum account leverage cap (10% risk fraction -> 15% risk money max)
        assert plan["risk_money"] <= 10000.0 * 0.15

        # Feed into broker
        res = pb.execute_trade(plan)
        assert res["status"] in ("filled", "skipped", "rejected")
        assert not math.isnan(pb.balance)
        assert not math.isinf(pb.balance)

    # Test broker resistance to explicit NaN lots/entry
    nan_plan = {"action": "BUY", "direction": "LONG", "entry": float("nan"), "lots": float("nan"), "feasible": True}
    res_nan = pb.execute_trade(nan_plan)
    assert res_nan["status"] in ("skipped", "rejected")
    assert pb.balance == 10000.0


# ===========================================================================
# 10. Auto Trade Loop WebSocket Disconnect & Stream Exhaustion
# ===========================================================================
@pytest.mark.asyncio
async def test_auto_trade_loop_websocket_disconnect_and_stream_exhaustion():
    """Verifies auto_trade_loop handles stream connection resets and abrupt
    termination gracefully without uncaught exceptions or crashing the task.
    """
    ticks_sent = 0

    async def flaky_socket_stream(*args, **kwargs):
        nonlocal ticks_sent
        ticks_sent += 1
        yield _make_base_candle(ticks_sent)
        await asyncio.sleep(0.01)
        # Simulates socket drop: ConnectionResetError
        raise ConnectionResetError("WebSocket connection reset by peer (code 1006)")

    with patch("app.market_data.providers.base.synth_websocket_stream", side_effect=flaky_socket_stream):
        task = asyncio.create_task(auto_trade_loop())
        # Allow supervisor loop to catch drop, reconnect, and sleep
        await asyncio.sleep(0.18)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert task.done()
        assert ticks_sent >= 1, "Expected at least 1 tick emitted before socket drop"
        exc = task.exception() if not task.cancelled() else None
        assert exc is None, f"Loop failed with unhandled exception: {exc}"


# ===========================================================================
# 11. Auto Trade Loop Corrupted Tick History Poisoning & Flash Crashes
# ===========================================================================
@pytest.mark.asyncio
async def test_auto_trade_loop_corrupted_tick_history_poisoning_and_flash_crashes():
    """Verifies corrupted ticks, flash spikes, flash crashes, and infinite volume
    ticks do not permanently poison history and recovery ticks process cleanly.
    """
    corrupted_and_extreme_sequence = [
        # 0: Normal baseline
        _make_base_candle(0, 2650.0),
        # 1: Corrupted tick (string price / invalid type)
        Candle(timestamp=int(time.time()) + 60, open=2650.0, high=2651.0, low=2649.0, close=2650.0, volume=100.0, source_type=SourceType.SPOT),
        # 2: Flash Spike (+100% price jump to 5300.0)
        Candle(timestamp=int(time.time()) + 120, open=5300.0, high=5310.0, low=5290.0, close=5300.0, volume=5000.0, source_type=SourceType.SPOT),
        # 3: Normal recovery tick
        _make_base_candle(3, 2650.0),
        # 4: Flash Crash (-80% price jump to 530.0)
        Candle(timestamp=int(time.time()) + 240, open=530.0, high=535.0, low=525.0, close=530.0, volume=10000.0, source_type=SourceType.SPOT),
        # 5: Infinite volume tick
        Candle(timestamp=int(time.time()) + 300, open=2650.0, high=2652.0, low=2648.0, close=2650.0, volume=float("inf"), source_type=SourceType.SPOT),
        # 6: Out-of-order timestamp (timestamp older than previous tick)
        Candle(timestamp=int(time.time()) - 3600, open=2650.0, high=2652.0, low=2648.0, close=2651.0, volume=1000.0, source_type=SourceType.SPOT),
        # 7: Valid recovery candle
        _make_base_candle(7, 2655.0),
    ]
    object.__setattr__(corrupted_and_extreme_sequence[1], "high", "corrupted_string_price")

    processed_evaluations = 0
    from app.strategy import engine as strat_engine
    orig_eval = strat_engine.evaluate_all

    def tracking_eval(*args, **kwargs):
        nonlocal processed_evaluations
        processed_evaluations += 1
        return orig_eval(*args, **kwargs)

    async def stress_tick_stream(*args, **kwargs):
        for t in corrupted_and_extreme_sequence:
            yield t
            await asyncio.sleep(0.01)

    with patch("app.market_data.providers.base.synth_websocket_stream", side_effect=stress_tick_stream), \
         patch("app.strategy.engine.evaluate_all", side_effect=tracking_eval):

        task = asyncio.create_task(auto_trade_loop())
        await asyncio.sleep(0.35)

        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert task.cancelled() or task.exception() is None
        # Verify that recovery ticks successfully reached strategy evaluation without permanent history poisoning
        assert processed_evaluations >= 2, f"History was poisoned! Only {processed_evaluations} ticks reached evaluation."


# ===========================================================================
# 12. Auto Trade Loop Live Concurrent Multi-Client Stress
# ===========================================================================
@pytest.mark.asyncio
async def test_auto_trade_loop_live_concurrent_multi_client_stress():
    """Stress tests auto_trade_loop running concurrently with 12 multi-threaded
    HTTP client workers performing rapid conflicting operations without deadlocks
    or ledger inconsistencies.
    """
    from starlette.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    client_errors = []
    stop_workers = threading.Event()

    async def continuous_stream(*args, **kwargs):
        i = 0
        while not stop_workers.is_set():
            yield _make_base_candle(i, 2650.0 + (i % 5) * 0.2)
            i += 1
            await asyncio.sleep(0.005)

    def client_worker(worker_id: int):
        headers = {"X-Forwarded-For": f"192.168.2.{10 + worker_id}"}
        for i in range(25):
            if stop_workers.is_set():
                break
            try:
                op = (worker_id + i) % 4
                if op == 0:
                    r = client.post("/api/v1/execution/close_all", json={"current_price": 2652.0}, headers=headers)
                    assert r.status_code in (200, 429)
                elif op == 1:
                    r = client.post("/api/v1/execution/trade", json={
                        "action": "BUY", "direction": "LONG", "entry": 2650.0, "lots": 0.05, "feasible": True
                    }, headers=headers)
                    assert r.status_code in (200, 429)
                elif op == 2:
                    r = client.get("/api/v1/execution/portfolio", headers=headers)
                    assert r.status_code in (200, 429)
                else:
                    r = client.get("/api/v1/market-data/candles?limit=50", headers=headers)
                    assert r.status_code in (200, 429)
            except Exception as err:
                client_errors.append((worker_id, err))

    with patch("app.market_data.providers.base.synth_websocket_stream", side_effect=continuous_stream):
        loop_task = asyncio.create_task(auto_trade_loop())

        # Launch 12 concurrent worker threads
        threads = [threading.Thread(target=client_worker, args=(wid,)) for wid in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        stop_workers.set()
        await asyncio.sleep(0.05)

        # Cancel auto_trade_loop while under load
        loop_task.cancel()
        try:
            await asyncio.wait_for(loop_task, timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

        assert len(client_errors) == 0, f"Encountered client concurrency exceptions: {client_errors}"
        assert loop_task.done()

        # Verify broker ledger invariant: balance must be finite and consistent
        portfolio = broker.get_portfolio()
        assert not math.isnan(portfolio["balance"])
        assert not math.isinf(portfolio["balance"])

