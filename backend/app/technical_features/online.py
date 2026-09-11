"""Online (incremental) indicators: O(1) amortized per bar, EXACT batch math.

Batch functions recompute O(W) values per bar to keep one. These carry the
recurrence state forward instead. Seeding mirrors the batch functions exactly
(simple averages over the first `period` inputs), so stepping through the same
bars yields bit-identical outputs to the batch versions (verified by test).

Use: prime with history in order, then step() one closed bar at a time.
Full memory (no trailing-window truncation) — also more faithful to live
trading than windowed recomputation.
"""
from __future__ import annotations
import math
from collections import deque


class EmaState:
    def __init__(self, period: int):
        self.period = period
        self.k = 2 / (period + 1)
        self._seed: list[float] = []
        self.value: float | None = None

    def step(self, x: float) -> float | None:
        if self.value is None:
            self._seed.append(x)
            if len(self._seed) < self.period:
                return None
            self.value = sum(self._seed) / self.period
            self._seed = []
            return self.value
        self.value = x * self.k + self.value * (1 - self.k)
        return self.value


class RsiState:
    def __init__(self, period: int = 14):
        self.period = period
        self._prev: float | None = None
        self._sg: list[float] = []
        self._sl: list[float] = []
        self._ag: float | None = None
        self._al: float | None = None
        self.value: float | None = None

    def step(self, close: float) -> float | None:
        if self._prev is None:
            self._prev = close
            return None
        d = close - self._prev
        self._prev = close
        g, l = (d, 0.0) if d > 0 else (0.0, -d)
        if self._ag is None:
            self._sg.append(g)
            self._sl.append(l)
            if len(self._sg) < self.period:
                return None
            self._ag = sum(self._sg) / self.period
            self._al = sum(self._sl) / self.period
            self._sg, self._sl = [], []
        else:
            self._ag = (self._ag * (self.period - 1) + g) / self.period
            self._al = (self._al * (self.period - 1) + l) / self.period
        self.value = 100 - 100 / (1 + self._ag / self._al) if self._al else 100.0
        return self.value


class AtrAdxState:
    """Wilder ATR + ADX. Index mapping vs batch (period p, n bars):
    batch trs[k] = TR of bar k+1; seed = mean(trs[:p]) = bars 1..p,
    first ATR at bar p; first DX at bar p+1; ADX seed after p DXs = bar 2p.

    Precision trap (documented, bit-verified): batch ADX keeps its smoothers
    as UNSCALED sums (seed = plain sum, smooth = s - s/p + x) while batch ATR
    outputs means. This class therefore keeps _satr/_sp/_sm as sums exactly
    like batch ADX, and exposes atr as _satr/p (identical to batch ATR)."""

    def __init__(self, period: int = 14):
        self.p = period
        self._prev: tuple[float, float, float] | None = None  # (h, l, c)
        self._trs: list[float] = []
        self._pm: list[float] = []
        self._mm: list[float] = []
        self._satr = 0.0
        self._sp = 0.0
        self._sm = 0.0
        self._dxs: list[float] = []
        self.atr: float | None = None
        self.adx: float | None = None

    def _dx(self) -> float:
        dip = 100 * self._sp / self._satr if self._satr else 0.0
        dim = 100 * self._sm / self._satr if self._satr else 0.0
        return 100 * abs(dip - dim) / (dip + dim) if (dip + dim) else 0.0

    def step(self, high: float, low: float, close: float) -> tuple[float | None, float | None]:
        p = self.p
        if self._prev is None:
            self._prev = (high, low, close)
            return None, None
        ph, pl, pc = self._prev
        self._prev = (high, low, close)
        up, dn = high - ph, pl - low
        tr = max(high - low, abs(high - pc), abs(low - pc))
        pm = up if up > dn and up > 0 else 0.0
        mm = dn if dn > up and dn > 0 else 0.0
        if self.atr is None:
            self._trs.append(tr)
            self._pm.append(pm)
            self._mm.append(mm)
            if len(self._trs) < p:
                return None, None
            self._satr = sum(self._trs[:p])
            self._sp = sum(self._pm[:p])
            self._sm = sum(self._mm[:p])
            self.atr = self._satr / p
            self._trs, self._pm, self._mm = [], [], []
            return self.atr, None
        # Sum-space smoothing, exactly like batch ADX; atr exposed as mean.
        self._satr = self._satr - self._satr / p + tr
        self._sp = self._sp - self._sp / p + pm
        self._sm = self._sm - self._sm / p + mm
        self.atr = self._satr / p
        if self.adx is None:
            self._dxs.append(self._dx())
            if len(self._dxs) < p:
                return self.atr, None
            self.adx = sum(self._dxs[:p]) / p
            self._dxs = []
            return self.atr, self.adx
        dx = self._dx()
        self.adx = (self.adx * (p - 1) + dx) / p
        return self.atr, self.adx


class MacdState:
    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        self._ef = EmaState(fast)
        self._es = EmaState(slow)
        self._sg = EmaState(signal)

    def step(self, close: float) -> tuple[float | None, float | None, float | None]:
        f, s = self._ef.step(close), self._es.step(close)
        if f is None or s is None:
            return None, None, None
        line = f - s
        sig = self._sg.step(line)
        if sig is None:
            return line, None, None
        return line, sig, line - sig


class RollingStats:
    """O(1) rolling mean/stddev over a fixed window (deque + running sums)."""

    def __init__(self, period: int):
        self.period = period
        self._q: deque[float] = deque()
        self._s = 0.0
        self._sq = 0.0

    def step(self, x: float) -> tuple[float, float] | None:
        self._q.append(x)
        self._s += x
        self._sq += x * x
        if len(self._q) > self.period:
            old = self._q.popleft()
            self._s -= old
            self._sq -= old * old
        if len(self._q) < self.period:
            return None
        m = self._s / self.period
        var = self._sq / self.period - m * m
        return m, math.sqrt(var) if var > 0 else 0.0
