"""Phase 6: BUY/SELL/NO-TRADE. Confidence vs Quality. Session gate, ARMED pullback, sweep confluence."""
import time

KILLZONES = ("LONDON", "NEW_YORK")

def pullback_ok(direction: str | None, closes: list[float]) -> bool:
    # 1-3 counter-trend closes in last 5 (cf. backtrader pullback window)
    if not direction or len(closes) < 6:
        return False
    last5 = [closes[i] - closes[i-1] for i in range(len(closes)-5, len(closes))]
    counter = sum(1 for d in last5 if (d < 0 if direction == "LONG" else d > 0))
    return 1 <= counter <= 3

def sweep_confluence(analysis: dict, direction: str | None) -> bool:
    if not direction:
        return False
    want = "SSL_SWEEP" if direction == "LONG" else "BSL_SWEEP"
    return any(s.get("type") == want for s in (analysis.get("sweeps") or []))

def _confidence(quality: int, volatility: str | None, rel_vol: float | None, sweep: bool) -> int:
    c = quality
    if volatility == "EXTREME_VOLATILITY":
        c -= 25
    elif volatility == "HIGH_VOLATILITY":
        c -= 5
    elif volatility == "LOW_VOLATILITY":
        c -= 10
    if rel_vol is not None:
        if rel_vol >= 1.2:
            c += 5
        elif rel_vol < 0.7:
            c -= 10
    if sweep:
        c += 10
    return max(0, min(100, c))

def resolve(evaluations: list[dict], volatility: str | None, rel_vol: float | None,
            session: str | None = None, closes: list[float] | None = None,
            analysis: dict | None = None, min_conf: int = 60) -> dict:
    quals = [e for e in evaluations if e.get("qualified") and e.get("direction")]
    if not quals:
        return {"action": "NO_TRADE", "strategy": None, "direction": None, "confidence": 0,
                "quality": 0, "state": "REJECTED",
                "reasons": ["no strategy qualified"] + [f"{e['strategy']}: {'; '.join(e.get('missing', []))}" for e in evaluations]}
    scored = []
    for e in quals:
        q = e.get("quality", 0)
        sw = sweep_confluence(analysis or {}, e.get("direction"))
        scored.append((q, _confidence(q, volatility, rel_vol, sw), e, sw))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    if len(scored) >= 2:
        (q1, c1, e1, _), (q2, c2, e2, _) = scored[0], scored[1]
        if e1["direction"] != e2["direction"] and abs(q1 - q2) < 10:
            return {"action": "NO_TRADE", "strategy": None, "direction": None,
                    "confidence": 0, "quality": 0, "state": "CONFLICT",
                    "reasons": [f"conflict {e1['strategy']} {e1['direction']} q={q1} vs {e2['strategy']} {e2['direction']} q={q2}"]}
    q, c, e, sw = scored[0]
    action = "BUY" if e["direction"] == "LONG" else "SELL"
    reasons = list(e.get("met", []))
    if sw:
        reasons.append("liquidity-sweep confluence +10")
    # session/killzone gate: outside LONDON/NY never CONFIRMED
    if session and session not in KILLZONES:
        return {"action": action, "strategy": e["strategy"], "direction": e["direction"],
                "confidence": c, "quality": q, "state": "PROPOSED",
                "reasons": reasons + [f"session {session} outside killzones LONDON/NEW_YORK — review only"],
                "trace": {"evaluations": evaluations, "volatility": volatility}}
    # ARMED pullback gate for trend continuation (SCANNING→ARMED→ENTRY)
    if e["strategy"] == "TREND_CONT" and not pullback_ok(e["direction"], closes or []):
        return {"action": action, "strategy": e["strategy"], "direction": e["direction"],
                "confidence": c, "quality": q, "state": "ARMED",
                "reasons": reasons + ["waiting pullback: need 1-3 counter-trend closes in last 5"],
                "trace": {"evaluations": evaluations, "volatility": volatility}}
    state = "CONFIRMED" if (c >= min_conf and q >= min_conf) else "PROPOSED"
    return {"action": action, "strategy": e["strategy"], "direction": e["direction"],
            "confidence": c, "quality": q, "state": state,
            "reasons": reasons, "trace": {"evaluations": evaluations, "volatility": volatility}}

def decide(evaluations: list[dict], features: dict, context: dict | None = None,
         min_conf: int = 60) -> dict:
    ctx = context or {}
    vol = features.get("volatility") or features.get("_volatility")
    out = resolve(evaluations, vol, features.get("rel_volume"), ctx.get("session"),
                  ctx.get("closes"), ctx.get("analysis"), min_conf)
    out["timestamp"] = int(time.time())
    return out
