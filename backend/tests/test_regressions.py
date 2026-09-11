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


def _trending_series(n=700, drift=0.8, noise=0.6, dip_at=300, dip_n=7, dip_depth=1.0, seed=12):
    """Deterministic trend -> pullback -> recovery. Pure noise must yield nothing;
    THIS series must yield at least one trade, proving the funnel flows."""
    import datetime
    import random
    from app.market_data.models import Candle, SourceType
    day = datetime.datetime.now(datetime.timezone.utc).replace(hour=6, minute=30, second=0, microsecond=0)
    t0 = int(day.timestamp())
    rng = random.Random(seed)
    px, cs = 2650.0, []
    for i in range(n):
        d = drift + rng.uniform(-noise, noise)
        if dip_at <= i < dip_at + dip_n:
            d -= dip_depth
        o, c = px, px + d
        cs.append(Candle(timestamp=t0 + i * 60, open=o, high=max(o, c) + 0.3,
                         low=min(o, c) - 0.3, close=c, volume=1500.0,
                         provider_instrument="XAU/USD", source="twelve_data",
                         source_type=SourceType.SPOT))
        px = c
    return cs


def test_backtest_produces_trades():
    # A backtest that silently trades nothing on a textbook setup is broken.
    # (Pure noise SHOULD yield ~0 — that assertion would demand trading randomness.)
    r = run_backtest(_trending_series())
    assert r["trades"] > 0, f"0 trades on trend+pullback+recovery: {r['gate_reasons']}"
