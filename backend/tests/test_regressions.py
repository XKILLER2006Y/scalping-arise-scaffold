"""Regression guards: silent-zero-trade bugs must never return."""
from app.market_data.providers.base import synth_candles
from app.market_data.models import SourceType
from app.backtesting.engine import run_backtest
from app.strategy.engine import eval_trend_cont


def _cs(n=400):
    return synth_candles("twelve_data", "XAU/USD", SourceType.SPOT, n=n)


def test_vol_bridge_both_key_shapes():
    # Evals must honor EITHER volatility key (callers differ). This exact mismatch
    # once zeroed every backtest in history.
    from app.technical_features.engine import compute_single_timeframe
    cs = _cs(250)
    f = compute_single_timeframe(cs, "1m")
    base = dict(f["features"])
    a = {"trend": "UPTREND", "bos": True}
    r1 = eval_trend_cont(a, {**base, "_volatility": "NORMAL_VOLATILITY", "rsi14": 60.0,
                             "ema20": 2.0, "ema50": 1.0, "adx14": 25.0, "atr_ratio": 1.0})
    r2 = eval_trend_cont(a, {**base, "volatility": "NORMAL_VOLATILITY", "rsi14": 60.0,
                             "ema20": 2.0, "ema50": 1.0, "adx14": 25.0, "atr_ratio": 1.0})
    assert not any("volatility" in m for m in r1["missing"])
    assert not any("volatility" in m for m in r2["missing"])


def test_enum_source_accepted():
    from app.strategy.eligibility import check_eligibility
    a = {"trend": "UPTREND"}
    f = {"ema20": 1.0, "rsi14": 55.0, "atr14": 2.0}
    for st in ("SPOT", "FUTURES_PROXY", "SourceType.SPOT", "SourceType.FUTURES_PROXY"):
        assert check_eligibility("TREND_CONT", a, f, 250, st)["eligible"], st


def test_backtest_produces_trades():
    # A backtest that silently trades nothing is a broken backtest.
    # NOTE: timestamps must span killzones (LONDON/NY) — the session gate
    # correctly vetoes OFF/ASIA bars, so a window stuck at night trades nothing.
    import datetime
    day = datetime.datetime.now(datetime.timezone.utc).replace(hour=6, minute=30, second=0, microsecond=0)
    start = int(day.timestamp())
    cs = synth_candles("twelve_data", "XAU/USD", SourceType.SPOT, n=700, start=start)
    r = run_backtest(cs)
    assert r["trades"] > 0, f"0 trades: {r['gate_reasons']}"
