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

def sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    for i in range(period - 1, len(values)):
        out[i] = sum(values[i - period + 1:i + 1]) / period
    return out

def zscore(closes: list[float], period: int = 20) -> list[float | None]:
    # (close - SMA) / StdDev, closed-bar only
    out: list[float | None] = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        w = closes[i - period + 1:i + 1]
        m = sum(w) / period
        var = sum((x - m) ** 2 for x in w) / period
        sd = math.sqrt(var)
        out[i] = (closes[i] - m) / sd if sd else 0.0
    return out

def adx(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float | None]:
    n = len(closes)
    out: list[float | None] = [None] * n
    if n < 2 * period + 1:
        return out
    pmap, mmap = [0.0] * n, [0.0] * n
    trs = [0.0] * n
    for i in range(1, n):
        up, dn = highs[i] - highs[i-1], lows[i-1] - lows[i]
        pmap[i] = up if up > dn and up > 0 else 0.0
        mmap[i] = dn if dn > up and dn > 0 else 0.0
        trs[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
    satr = sum(trs[1:period+1])
    sp, sm = sum(pmap[1:period+1]), sum(mmap[1:period+1])
    dxs: list[float] = []
    for i in range(period + 1, n):
        satr = satr - satr / period + trs[i]
        sp = sp - sp / period + pmap[i]
        sm = sm - sm / period + mmap[i]
        dip = 100 * sp / satr if satr else 0.0
        dim = 100 * sm / satr if satr else 0.0
        dxs.append(100 * abs(dip - dim) / (dip + dim) if (dip + dim) else 0.0)
    if len(dxs) < period:
        return out
    a = sum(dxs[:period]) / period
    out[2 * period] = a
    for k in range(period, len(dxs)):
        a = (a * (period - 1) + dxs[k]) / period
        out[2 * period + (k - period + 1)] = a
    return out

def vwap(highs: list[float], lows: list[float], closes: list[float], volumes: list[float | None]) -> list[float | None]:
    # session-agnostic cumulative VWAP over given window; caller resets per session
    out: list[float | None] = [None] * len(closes)
    pv, vv = 0.0, 0.0
    for i in range(len(closes)):
        v = volumes[i] if i < len(volumes) and volumes[i] else 0.0
        tp = (highs[i] + lows[i] + closes[i]) / 3
        pv += tp * v; vv += v
        out[i] = (pv / vv) if vv else None
    return out

def cvd(opens: list[float], highs: list[float], lows: list[float], closes: list[float], volumes: list[float | None]) -> list[float | None]:
    """Cumulative Volume Delta: Pseudo Order Flow Imbalance (OFI) proxy based on intra-candle price action."""
    out: list[float | None] = [None] * len(closes)
    cum_delta = 0.0
    for i in range(len(closes)):
        v = volumes[i] if i < len(volumes) and volumes[i] else 0.0
        h, l, c = highs[i], lows[i], closes[i]
        rng = h - l
        if rng > 0:
            buy_pressure = (c - l) / rng
            ofi_proxy = (buy_pressure - 0.5) * v
        else:
            ofi_proxy = 0.0
        cum_delta += ofi_proxy
        out[i] = cum_delta
    return out

def garman_klass(opens: list[float], highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float | None]:
    """Garman-Klass Volatility: incorporates O/H/L/C for better variance estimation."""
    out: list[float | None] = [None] * len(closes)
    gk_vals = []
    for i in range(len(closes)):
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        if (
            o is not None and h is not None and l is not None and c is not None
            and o > 0 and h > 0 and l > 0 and c > 0
            and not any(math.isnan(x) or math.isinf(x) for x in (o, h, l, c))
        ):
            try:
                gk = 0.5 * math.log(h / l)**2 - (2 * math.log(2) - 1) * math.log(c / o)**2
                # Avoid negative roots due to floating point drift
                gk_vals.append(max(0.0, gk))
            except (ValueError, ZeroDivisionError):
                gk_vals.append(0.0)
        else:
            gk_vals.append(0.0)

    for i in range(period - 1, len(closes)):
        w = gk_vals[i - period + 1:i + 1]
        out[i] = math.sqrt(sum(w) / period)
    return out

def volume_profile(closes: list[float], volumes: list[float | None], bins: int = 10) -> dict:
    """Calculate Volume Profile and Point of Control (POC) for the given window."""
    clean = []
    for i, c in enumerate(closes):
        if c is not None and not math.isnan(c) and not math.isinf(c) and c > 0:
            v = volumes[i] if i < len(volumes) and volumes[i] is not None and not math.isnan(volumes[i]) and not math.isinf(volumes[i]) and volumes[i] > 0 else 0.0
            clean.append((c, v))

    if not clean:
        return {"poc": None, "profile": {}}

    clean_closes = [x[0] for x in clean]
    min_px, max_px = min(clean_closes), max(clean_closes)
    if min_px == max_px or bins <= 0:
        return {"poc": min_px, "profile": {min_px: sum(x[1] for x in clean)}}

    bin_size = (max_px - min_px) / bins
    if bin_size <= 0:
        return {"poc": min_px, "profile": {min_px: sum(x[1] for x in clean)}}

    profile = {}
    for c, v in clean:
        idx = math.floor((c - min_px) / bin_size)
        b = round(min_px + idx * bin_size, 2)
        profile[b] = profile.get(b, 0.0) + v

    poc = max(profile.items(), key=lambda x: x[1])[0] if profile else None
    return {"poc": poc, "profile": profile}

