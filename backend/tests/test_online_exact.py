"""Online indicators must reproduce batch math (bit-exact where op order allows)."""
import random
from app.technical_features import indicators as I
from app.technical_features.online import EmaState, RsiState, AtrAdxState, MacdState, RollingStats


def _data(seed=42, n=300, base=500.0):
    rng = random.Random(seed)
    px, H, L, C = base, [], [], []
    for _ in range(n):
        o = px
        c = px + rng.uniform(-1.5, 1.5)
        H.append(max(o, c) + rng.random())
        L.append(min(o, c) - rng.random())
        C.append(c)
        px = c
    return H, L, C


def _assert_same(name, online, batch, tol):
    assert len(online) == len(batch)
    worst = 0.0
    for a, b in zip(online, batch):
        assert (a is None) == (b is None), f"{name}: None-placement differs"
        if a is not None:
            worst = max(worst, abs(a - b))
    assert worst <= tol, f"{name}: max diff {worst} exceeds {tol}"
    return worst


def test_online_matches_batch():
    H, L, C = _data()
    assert _assert_same("EMA20", _run_ema(C), I.ema(C, 20), 0.0) == 0.0
    r = RsiState(14)
    assert _assert_same("RSI14", [r.step(x) for x in C], I.rsi(C, 14), 0.0) == 0.0
    aa = AtrAdxState(14)
    vals = [aa.step(h, l, c) for h, l, c in zip(H, L, C)]
    assert _assert_same("ATR14", [v[0] for v in vals], I.atr(H, L, C, 14), 1e-12) <= 1e-12
    assert _assert_same("ADX14", [v[1] for v in vals], I.adx(H, L, C, 14), 0.0) == 0.0
    m = MacdState()
    outs = [m.step(c) for c in C]
    bl, bs, bh = I.macd(C)
    assert _assert_same("MACD-line", [o[0] for o in outs], bl, 0.0) == 0.0
    assert _assert_same("MACD-sig", [o[1] for o in outs], bs, 0.0) == 0.0
    rs = RollingStats(20)
    outs = [rs.step(x) for x in C]
    bm, _, _ = I.bollinger(C)
    assert _assert_same("BB-mid", [o[0] if o else None for o in outs], bm, 1e-9) <= 1e-9


def _run_ema(C):
    e = EmaState(20)
    return [e.step(x) for x in C]
