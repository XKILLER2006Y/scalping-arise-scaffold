"""Phase 4 CORE indicators. Pure functions, no look-ahead: value[i] uses closes[:i+1] only."""
import math

def ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period or period <= 0:
        return out
    k = 2 / (period + 1)
    s = sum(values[:period]) / period
    out[period - 1] = s
    for i in range(period, len(values)):
        s = values[i] * k + s * (1 - k)
        out[i] = s
    return out

def rsi(closes: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    if len(closes) < period + 1:
        return out
    gains, losses = [], []
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    ag = sum(gains) / period; al = sum(losses) / period
    out[period] = 100 - 100 / (1 + ag / al) if al else 100.0
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (period - 1) + max(d, 0)) / period
        al = (al * (period - 1) + max(-d, 0)) / period
        out[i] = 100 - 100 / (1 + ag / al) if al else 100.0
    return out

def macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9):
    ef, es = ema(closes, fast), ema(closes, slow)
    line: list[float | None] = [None] * len(closes)
    for i in range(len(closes)):
        if ef[i] is not None and es[i] is not None:
            line[i] = ef[i] - es[i]  # type: ignore
    vals = [v for v in line if v is not None]
    sig = ema(vals, signal)
    # align
    sig_full: list[float | None] = [None] * len(closes)
    j = 0
    first = next((i for i, v in enumerate(line) if v is not None), None)
    if first is not None:
        for i in range(first, len(closes)):
            if j < len(sig):
                sig_full[i] = sig[j]; j += 1
    hist = [None if line[i] is None or sig_full[i] is None else line[i] - sig_full[i] for i in range(len(closes))]
    return line, sig_full, hist

def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    if len(closes) < period + 1:
        return out
    trs = []
    for i in range(1, len(closes)):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
    a = sum(trs[:period]) / period
    out[period] = a
    for i in range(period + 1, len(closes)):
        idx = i - 1
        a = (a * (period - 1) + trs[idx]) / period
        out[i] = a
    return out

def bollinger(closes: list[float], period: int = 20, std: float = 2.0):
    mid: list[float | None] = [None] * len(closes)
    up: list[float | None] = [None] * len(closes)
    lo: list[float | None] = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        w = closes[i - period + 1:i + 1]
        m = sum(w) / period
        var = sum((x - m) ** 2 for x in w) / period
        sd = math.sqrt(var)
        mid[i] = m; up[i] = m + std * sd; lo[i] = m - std * sd
    return mid, up, lo
