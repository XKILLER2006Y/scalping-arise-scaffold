"""Phase 6: BUY/SELL/NO-TRADE. Confidence vs Quality. Conflict resolver. State machine."""
import time

def _confidence(quality: int, volatility: str | None, rel_vol: float | None) -> int:
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
    return max(0, min(100, c))

def resolve(evaluations: list[dict], volatility: str | None, rel_vol: float | None) -> dict:
    quals = [e for e in evaluations if e.get("qualified") and e.get("direction")]
    if not quals:
        return {"action": "NO_TRADE", "strategy": None, "direction": None, "confidence": 0,
                "quality": 0, "state": "REJECTED",
                "reasons": ["no strategy qualified"] + [f"{e['strategy']}: {'; '.join(e.get('missing', []))}" for e in evaluations]}
    scored = []
    for e in quals:
        q = e.get("quality", 0)
        scored.append((q, _confidence(q, volatility, rel_vol), e))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    if len(scored) >= 2:
        (q1, c1, e1), (q2, c2, e2) = scored[0], scored[1]
        if e1["direction"] != e2["direction"] and abs(q1 - q2) < 10:
            return {"action": "NO_TRADE", "strategy": None, "direction": None,
                    "confidence": 0, "quality": 0, "state": "CONFLICT",
                    "reasons": [f"conflict {e1['strategy']} {e1['direction']} q={q1} vs {e2['strategy']} {e2['direction']} q={q2}"]}
    q, c, e = scored[0]
    action = "BUY" if e["direction"] == "LONG" else "SELL"
    state = "CONFIRMED" if (c >= 60 and q >= 60) else "PROPOSED"
    return {"action": action, "strategy": e["strategy"], "direction": e["direction"],
            "confidence": c, "quality": q, "state": state,
            "reasons": e.get("met", []), "trace": {"evaluations": evaluations, "volatility": volatility}}

def decide(evaluations: list[dict], features: dict) -> dict:
    vol = features.get("volatility") or features.get("_volatility")
    out = resolve(evaluations, vol, features.get("rel_volume"))
    out["timestamp"] = int(time.time())
    return out
