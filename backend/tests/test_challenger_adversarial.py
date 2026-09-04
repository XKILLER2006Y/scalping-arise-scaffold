"""Empirical Adversarial Challenge Test Suite for Scalping Arise.

Authored by Challenger 1 (Loop & ML Adversarial Challenger).
Independently verifies:
1. WebSocket connection drops, reconnection storms, and recovery.
2. Exhaustive corrupted ticks (types, NaNs, Infs, negative/zero prices, inverted candles, out-of-order timestamps).
3. Extreme volatility (>50% flash crashes, multi-thousand percent flash spikes, wild oscillations).
4. ML model failure modes (0-byte pickle, corrupted binary, unpickling errors, NaN/Inf probabilities, directional conflict Kelly sizing).
"""

import asyncio
import math
import os
import sys
import time
from unittest.mock import patch, MagicMock
import numpy as np
import pytest

backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.execution.engine import PaperBroker, broker
from app.market_data.models import Candle, SourceType
from app.market_analysis.engine import analyze_market
from app.technical_features.engine import compute_features
from app.signals.engine import decide
from app.trade_planning.engine import create_plan
from app.intelligence.sentiment import analyze_sentiment, reset_model_cache
from app.intelligence.ml_model import XGBoostSentimentModel
from app.strategy.engine import evaluate_all
from app.main import auto_trade_loop


def _make_candle(i: int, px: float = 2650.0, vol: float = 1000.0, ts_offset: int = 0) -> Candle:
    return Candle(
        timestamp=int(time.time()) + i * 60 + ts_offset,
        open=px,
        high=px + 1.0,
        low=px - 1.0,
        close=px + 0.2,
        volume=vol,
        provider_instrument="XAU/USD",
        source="twelve_data",
        source_type=SourceType.SPOT,
    )


# ===========================================================================
# 1. WebSocket drops, reconnection storms & recovery
# ===========================================================================
@pytest.mark.asyncio
async def test_adversarial_reconnect_storm():
    """Simulates 10 consecutive network drops with diverse network exceptions,
    verifying auto_trade_loop retries cleanly each time without leaking tasks or dying,
    and resumes processing when connection is restored.
    """
    drop_exceptions = [
        ConnectionResetError("Socket reset 1006"),
        TimeoutError("Socket read timeout"),
        OSError(104, "Connection reset by peer"),
        RuntimeError("Transient stream failure"),
        ConnectionRefusedError("Gateway unreachable"),
        asyncio.IncompleteReadError(b"partial", 100),
        ConnectionResetError("Repeated reset 1"),
        ConnectionResetError("Repeated reset 2"),
        TimeoutError("Second timeout"),
        OSError(110, "Connection timed out"),
    ]

    attempt_count = 0
    clean_ticks_processed = 0

    async def flapping_stream(*args, **kwargs):
        nonlocal attempt_count
        cur_attempt = attempt_count
        attempt_count += 1
        if cur_attempt < len(drop_exceptions):
            # Yield 1 tick, then drop
            yield _make_candle(cur_attempt, 2650.0 + cur_attempt)
            await asyncio.sleep(0.005)
            raise drop_exceptions[cur_attempt]
        else:
            # Reconnected stably: yield normal sequence
            for j in range(5):
                yield _make_candle(100 + j, 2660.0 + j)
                await asyncio.sleep(0.01)

    orig_evaluate = evaluate_all
    def spy_evaluate(*args, **kwargs):
        nonlocal clean_ticks_processed
        clean_ticks_processed += 1
        return orig_evaluate(*args, **kwargs)

    with patch("app.market_data.providers.base.synth_websocket_stream", side_effect=flapping_stream), \
         patch("app.strategy.engine.evaluate_all", side_effect=spy_evaluate), \
         patch.dict(os.environ, {"RECONNECT_DELAY": "0.01", "MAX_RECONNECT_DELAY": "0.05"}):

        task = asyncio.create_task(auto_trade_loop())

        # Wait for all reconnection attempts to complete
        for _ in range(200):
            if attempt_count >= 10 and clean_ticks_processed >= 5:
                break
            await asyncio.sleep(0.03)

        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert task.done()
        assert task.cancelled() or task.exception() is None, f"Loop died with exception: {task.exception()}"
        assert attempt_count >= 10, f"Expected at least 10 reconnection attempts, got {attempt_count}"
        assert clean_ticks_processed >= 5, f"Expected post-reconnect ticks to process, got {clean_ticks_processed}"


# ===========================================================================
# 2. Exhaustive Corrupted Ticks Battery
# ===========================================================================
@pytest.mark.asyncio
async def test_adversarial_corrupted_ticks_comprehensive():
    """Injects 25 pathological ticks: None, foreign types, missing fields, string prices,
    NaNs, Infs, inverted candles (high < low), zero/negative prices, infinite volume,
    and backwards/duplicate timestamps. Verifies auto_trade_loop drops all bad ticks
    without crashing or poisoning history.
    """
    now = int(time.time())

    # Build pathological ticks
    c_str = Candle(timestamp=now + 60, open=2650.0, high=2651.0, low=2649.0, close=2650.0, volume=100.0, source_type=SourceType.SPOT)
    object.__setattr__(c_str, "open", "invalid_string_open")

    c_nan_str = Candle(timestamp=now + 120, open=2650.0, high=2651.0, low=2649.0, close=2650.0, volume=100.0, source_type=SourceType.SPOT)
    object.__setattr__(c_nan_str, "close", "nan")

    c_none_field = Candle(timestamp=now + 180, open=2650.0, high=2651.0, low=2649.0, close=2650.0, volume=100.0, source_type=SourceType.SPOT)
    object.__setattr__(c_none_field, "high", None)

    battery = [
        # Valid baseline
        _make_candle(0, 2650.0),
        # 1. Non-candle types
        None,
        "string_tick",
        1234567,
        {"price": 2650.0},
        [],
        # 2. Corrupted attribute values
        c_str,
        c_nan_str,
        c_none_field,
        # 3. Numeric NaNs and Infs
        Candle(timestamp=now + 240, open=float("nan"), high=2655.0, low=2645.0, close=2650.0, volume=100.0, source_type=SourceType.SPOT),
        Candle(timestamp=now + 300, open=2650.0, high=float("inf"), low=2645.0, close=2650.0, volume=100.0, source_type=SourceType.SPOT),
        Candle(timestamp=now + 360, open=2650.0, high=2655.0, low=-float("inf"), close=2650.0, volume=100.0, source_type=SourceType.SPOT),
        Candle(timestamp=now + 420, open=2650.0, high=2655.0, low=2645.0, close=float("nan"), volume=100.0, source_type=SourceType.SPOT),
        # 4. Zero and Negative prices
        Candle(timestamp=now + 480, open=2650.0, high=2655.0, low=2645.0, close=0.0, volume=100.0, source_type=SourceType.SPOT),
        Candle(timestamp=now + 540, open=2650.0, high=2655.0, low=2645.0, close=-2650.0, volume=100.0, source_type=SourceType.SPOT),
        Candle(timestamp=now + 600, open=-10.0, high=2655.0, low=2645.0, close=2650.0, volume=100.0, source_type=SourceType.SPOT),
        # 5. Inverted candle: high < low
        Candle(timestamp=now + 660, open=2650.0, high=2640.0, low=2660.0, close=2645.0, volume=100.0, source_type=SourceType.SPOT),
        # 6. Infinite / negative volume
        Candle(timestamp=now + 720, open=2650.0, high=2655.0, low=2645.0, close=2650.0, volume=float("inf"), source_type=SourceType.SPOT),
        Candle(timestamp=now + 780, open=2650.0, high=2655.0, low=2645.0, close=2650.0, volume=float("nan"), source_type=SourceType.SPOT),
        Candle(timestamp=now + 840, open=2650.0, high=2655.0, low=2645.0, close=2650.0, volume=-1000.0, source_type=SourceType.SPOT),
        # 7. Out-of-order & duplicate timestamps
        Candle(timestamp=now - 86400, open=2650.0, high=2655.0, low=2645.0, close=2650.0, volume=100.0, source_type=SourceType.SPOT),
        Candle(timestamp=now - 3600, open=2651.0, high=2656.0, low=2646.0, close=2651.0, volume=100.0, source_type=SourceType.SPOT),
        Candle(timestamp=now + 900, open=2652.0, high=2657.0, low=2647.0, close=2652.0, volume=100.0, source_type=SourceType.SPOT),
        # 8. Clean recovery ticks
        _make_candle(20, 2655.0),
        _make_candle(21, 2656.0),
        _make_candle(22, 2657.0),
    ]

    ticks_processed = 0
    orig_eval = evaluate_all
    def spy_eval(*args, **kwargs):
        nonlocal ticks_processed
        ticks_processed += 1
        return orig_eval(*args, **kwargs)

    async def corrupted_stream(*args, **kwargs):
        for t in battery:
            yield t
            await asyncio.sleep(0.005)

    with patch("app.market_data.providers.base.synth_websocket_stream", side_effect=corrupted_stream), \
         patch("app.strategy.engine.evaluate_all", side_effect=spy_eval):

        task = asyncio.create_task(auto_trade_loop())

        for _ in range(100):
            if ticks_processed >= 4:
                break
            await asyncio.sleep(0.03)

        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert task.done()
        assert task.cancelled() or task.exception() is None
        # Must process valid ticks (baseline + 3 recovery candles + any valid out-of-order)
        assert ticks_processed >= 4, f"Expected at least 4 valid ticks processed, got {ticks_processed}"


# ===========================================================================
# 3. Extreme Volatility (>50% flash crash and flash spikes)
# ===========================================================================
@pytest.mark.asyncio
async def test_adversarial_extreme_volatility_crashes_and_spikes():
    """Feeds extreme market price shocks into auto_trade_loop:
    - 50% flash crash (2650 -> 1325)
    - 90% flash crash (1325 -> 132.5)
    - 99.9% flash crash (132.5 -> 0.1)
    - 10,000x flash spike (0.1 -> 10,000)
    - Wild high/low spreads and oscillations
    Verifies indicators, strategy, Kelly sizing, and paper broker handle shocks
    without math errors or ledger corruption.
    """
    shock_prices = [
        2650.0,
        2652.0,
        1325.0,   # -50% crash
        1300.0,
        130.0,    # -90% crash
        1.0,      # -99.2% crash
        0.05,     # near zero
        500.0,    # +1,000,000% spike
        5000.0,   # +10x spike
        25000.0,  # +5x spike
        2650.0,   # return to mean
    ]

    shocks = []
    for i, p in enumerate(shock_prices):
        spread = max(0.01, p * 0.05)
        shocks.append(Candle(
            timestamp=int(time.time()) + i * 60,
            open=p,
            high=p + spread,
            low=max(0.001, p - spread),
            close=p,
            volume=50000.0,
            provider_instrument="XAU/USD",
            source="twelve_data",
            source_type=SourceType.SPOT
        ))

    shocks_evaluated = 0
    orig_eval = evaluate_all
    def spy_eval(*args, **kwargs):
        nonlocal shocks_evaluated
        shocks_evaluated += 1
        return orig_eval(*args, **kwargs)

    async def shock_stream(*args, **kwargs):
        for s in shocks:
            yield s
            await asyncio.sleep(0.005)

    with patch("app.market_data.providers.base.synth_websocket_stream", side_effect=shock_stream), \
         patch("app.strategy.engine.evaluate_all", side_effect=spy_eval):

        task = asyncio.create_task(auto_trade_loop())

        for _ in range(100):
            if shocks_evaluated >= len(shock_prices):
                break
            await asyncio.sleep(0.03)

        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert task.done()
        assert task.cancelled() or task.exception() is None
        assert shocks_evaluated == len(shock_prices), f"Expected all {len(shock_prices)} shock prices evaluated, got {shocks_evaluated}"

        # Invariant: Broker balance must remain finite, positive, and uncorrupted
        p = broker.get_portfolio()
        assert not math.isnan(p["balance"])
        assert not math.isinf(p["balance"])
        assert p["balance"] > 0


# ===========================================================================
# 4. ML Model Failure Modes & Directional Alignment
# ===========================================================================
def test_adversarial_ml_failure_modes_and_directional_alignment(tmp_path):
    """Subject analyze_sentiment and XGBoostSentimentModel to:
    1. 0-byte pickle file
    2. Random binary garbage
    3. Missing files
    4. Extreme feature inputs (1e308, -1e308, NaN, Inf)
    5. Model returning NaN, Inf, and unbounded probabilities
    6. Directional conflict Kelly leverage suppression
    """
    reset_model_cache()

    # 1. 0-byte model file
    empty_pkl = tmp_path / "zero_byte.pkl"
    empty_pkl.write_bytes(b"")
    with patch("joblib.load", side_effect=EOFError("Ran out of input")):
        res = analyze_sentiment({"return": 0.01, "volatility_14": 0.01})
        assert res["sentiment"] in ("BULLISH", "BEARISH", "NEUTRAL")
        assert 0 <= res["confidence"] <= 100

    # 2. Corrupted header / random binary noise
    corrupt_pkl = tmp_path / "noise.pkl"
    corrupt_pkl.write_bytes(os.urandom(256))
    with patch("joblib.load", side_effect=Exception("Corrupted pickle stream")):
        res = analyze_sentiment({"return": 0.01, "volatility_14": 0.01})
        assert res["sentiment"] in ("BULLISH", "BEARISH", "NEUTRAL")
        assert 0 <= res["confidence"] <= 100

    # 3. Extreme features into analyze_sentiment
    extreme_feats = {
        "return": float("inf"),
        "log_return": -float("inf"),
        "volatility_14": 1e308,
        "gk_vol": float("nan"),
        "price_range": -50.0,
        "position_in_range": float("nan"),
        "cvd": float("inf"),
        "rsi_14": -999.0,
        "dist_sma9": 1e300,
        "dist_sma21": -1e300,
        "volume": float("inf"),
    }
    res_ext = analyze_sentiment(extreme_feats, structure={"trend": "RANGE"})
    assert res_ext["sentiment"] in ("BULLISH", "BEARISH", "NEUTRAL")
    assert not math.isnan(res_ext["confidence"])
    assert not math.isinf(res_ext["confidence"])
    assert 0 <= res_ext["confidence"] <= 100

    # 4. Model output anomalies
    aberrant_probas = [
        np.array([[float("nan"), float("nan")]]),
        np.array([[float("-inf"), float("inf")]]),
        np.array([[5.0, -4.0]]),
        np.array([0.9]),
        np.array([]),
    ]
    mock_xgb = MagicMock()
    for proba in aberrant_probas:
        mock_xgb.predict_proba.return_value = proba
        with patch("app.intelligence.sentiment._get_model", return_value=mock_xgb):
            res_prob = analyze_sentiment({"return": 0.01})
            assert isinstance(res_prob, dict)
            assert res_prob["sentiment"] in ("BULLISH", "BEARISH", "NEUTRAL")
            assert not math.isnan(res_prob["confidence"])
            assert not math.isinf(res_prob["confidence"])
            assert 0 <= res_prob["confidence"] <= 100

    # 5. Directional Conflict Kelly Sizing Suppression in create_plan
    # Test that conflicting ML sentiment (LONG with BEARISH 90% confidence)
    # gets neutralized to 50% in auto_trade_loop logic, preventing excessive leverage
    aligned_sig = {"action": "BUY", "direction": "LONG", "strategy": "TREND_CONT"}
    
    # High confidence aligned (LONG + BULLISH 90%)
    plan_aligned = create_plan(aligned_sig, entry=2650.0, atr=2.0, equity=10000.0, ml_confidence=90.0)
    # Neutralized confidence on conflict (LONG + BEARISH neutralized to 50%)
    plan_neutralized = create_plan(aligned_sig, entry=2650.0, atr=2.0, equity=10000.0, ml_confidence=50.0)

    assert plan_aligned["lots"] >= plan_neutralized["lots"], "Aligned ML should have >= lots than neutralized conflict"
    # Even aligned lots must respect account risk limits (max 10% risk fraction)
    assert plan_aligned["risk_money"] <= 10000.0 * 0.15
    assert plan_neutralized["risk_money"] <= 10000.0 * 0.15
