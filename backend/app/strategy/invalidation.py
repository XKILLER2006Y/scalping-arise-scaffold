"""Invalidation rules (Phase 5 companion).

Adapted with permission from Hash-sudo-cell/scalping-arise
(backend/app/modules/strategies/invalidation.py) to our dict-based pipeline.
Our analysis dicts carry: trend, regime, bos (bool), choch (bool),
support/resistance, sweeps [{type: SSL_SWEEP|BSL_SWEEP, i, level}], fvgs.

A triggered rule VETOES the setup: evaluate_all() marks it unqualified.
Approximations vs the original are noted per rule (we lack oriented
BOS/CHOCH events and pool strength metadata).
"""
from __future__ import annotations

# strategy_id -> rule_ids (mirrors friend's definitions.py rule lists)
STRATEGY_RULES: dict[str, list[str]] = {
    "TREND_CONT": ["tc_inval_choch", "tc_inval_regime_shift", "tc_liq_inval_opposing_sweep"],
    "PULLBACK_CONT": ["pc_inval_structure_break", "pc_inval_regime_shift",
                      "pc_inval_deep_pullback", "pc_liq_inval_opposing_sweep"],
    "RANGE_FADE": ["rr_inval_regime_change", "rr_inval_breakout", "rr_liq_inval_acceptance_after_sweep"],
}

RULE_NAMES = {
    "tc_inval_choch": "CHOCH Against Trend",
    "tc_inval_regime_shift": "Regime Shift to Ranging",
    "tc_liq_inval_opposing_sweep": "Opposing Sweep Detected",
    "pc_inval_structure_break": "Structure Break Against Trend",
    "pc_inval_regime_shift": "Regime Shift to Ranging",
    "pc_inval_deep_pullback": "Deep Pullback (>61.8%)",
    "pc_liq_inval_opposing_sweep": "Opposing Sweep Against Trend",
    "rr_inval_regime_change": "Regime Change to Trending",
    "rr_inval_breakout": "Range Breakout",
    "rr_liq_inval_acceptance_after_sweep": "Acceptance After Sweep",
}


def _res(rule_id: str, triggered: bool, reason: str, evidence: list | None = None) -> dict:
    return {"rule_id": rule_id, "rule_name": RULE_NAMES[rule_id],
            "triggered": triggered, "reason": reason, "evidence": evidence or []}


def _opposing_sweep(sweeps: list, direction: str | None) -> list:
    if not direction:
        return []
    want = "SSL_SWEEP" if direction == "LONG" else "BSL_SWEEP"
    # Approximation: our sweeps carry no strength metadata; treat any opposing sweep as relevant.
    return [s for s in sweeps if s.get("type") == want]


def evaluate_invalidation(strategy_id: str, analysis: dict, direction: str | None,
                          features: dict, closes: list[float] | None = None) -> list[dict]:
    closes = closes or []
    atr = features.get("atr14") or 0
    out: list[dict] = []
    for rule_id in STRATEGY_RULES.get(strategy_id, []):
        out.append(_EVALUATORS[rule_id](analysis, direction, features, closes, atr))
    return out


def _tc_choch(analysis, direction, features, closes, atr):
    if analysis.get("choch") and direction:
        return _res("tc_inval_choch", True,
                    f"CHOCH detected while positioned {direction} — trend may be flipping")
    return _res("tc_inval_choch", False, "No CHOCH against trend direction")


def _tc_regime(analysis, direction, features, closes, atr):
    if (analysis.get("trend") or "") == "RANGE":
        return _res("tc_inval_regime_shift", True, "Regime shifted to ranging — trend setup invalid")
    return _res("tc_inval_regime_shift", False, f"Trend intact ({analysis.get('trend')})")


def _tc_opp_sweep(analysis, direction, features, closes, atr):
    opp = _opposing_sweep(analysis.get("sweeps") or [], direction)
    if opp:
        return _res("tc_liq_inval_opposing_sweep", True,
                    f"Opposing sweep against {direction}", [f"level={s.get('level')}" for s in opp])
    return _res("tc_liq_inval_opposing_sweep", False, "No opposing sweep")


def _pc_struct_break(analysis, direction, features, closes, atr):
    # Approximation: our BOS is undirected, so confirm with adverse excursion:
    # close moved against direction by >0.5*ATR while a BOS printed.
    if analysis.get("bos") and direction and closes and atr:
        adverse = (closes[0] - closes[-1]) if direction == "LONG" else (closes[-1] - closes[0])
        if adverse > 0.5 * atr:
            return _res("pc_inval_structure_break", True,
                        f"BOS + adverse excursion {adverse:.2f} > 0.5*ATR against {direction}")
    if analysis.get("bos"):
        return _res("pc_inval_structure_break", False, "BOS present but no adverse excursion — pullback intact")
    return _res("pc_inval_structure_break", False, "No structure break against trend")


def _pc_regime(analysis, direction, features, closes, atr):
    if (analysis.get("trend") or "") == "RANGE":
        return _res("pc_inval_regime_shift", True, "Regime shifted to ranging — pullback setup invalid")
    return _res("pc_inval_regime_shift", False, "Still trending")


def _pc_deep_pullback(analysis, direction, features, closes, atr):
    # Retrace depth of the pullback vs prior 20-bar impulse; >61.8% = not a pullback anymore.
    if direction and len(closes) >= 25:
        base = closes[-25:-5]
        pull = closes[-5:]
        if direction == "LONG":
            high, low0 = max(base), min(base)
            impulse = high - low0
            depth = (high - min(pull)) / impulse if impulse > 0 else 0
        else:
            low, high0 = min(base), max(base)
            impulse = high0 - low
            depth = (max(pull) - low) / impulse if impulse > 0 else 0
        if depth > 0.618:
            return _res("pc_inval_deep_pullback", True,
                        f"Pullback retraced {depth:.1%} of impulse (>61.8%)")
        return _res("pc_inval_deep_pullback", False, f"Pullback depth {depth:.1%} within range")
    return _res("pc_inval_deep_pullback", False, "Insufficient closes for depth check")


def _pc_opp_sweep(analysis, direction, features, closes, atr):
    opp = _opposing_sweep(analysis.get("sweeps") or [], direction)
    if opp:
        return _res("pc_liq_inval_opposing_sweep", True,
                    f"Opposing sweep against {direction}", [f"level={s.get('level')}" for s in opp])
    return _res("pc_liq_inval_opposing_sweep", False, "No opposing sweep")


def _rr_regime(analysis, direction, features, closes, atr):
    if (analysis.get("trend") or "") in ("UPTREND", "DOWNTREND"):
        return _res("rr_inval_regime_change", True,
                    f"Regime is {analysis.get('trend')} — range setup invalid")
    return _res("rr_inval_regime_change", False, "Still ranging")


def _rr_breakout(analysis, direction, features, closes, atr):
    if analysis.get("bos"):
        return _res("rr_inval_breakout", True, "BOS in ranging market — possible breakout, fade invalid")
    return _res("rr_inval_breakout", False, "No breakout")


def _rr_acceptance(analysis, direction, features, closes, atr):
    # Acceptance = sweep printed but price HELD beyond the pool level (no rejection).
    if not closes:
        return _res("rr_liq_inval_acceptance_after_sweep", False, "No closes to judge acceptance")
    last = closes[-1]
    for s in analysis.get("sweeps") or []:
        lvl = s.get("level")
        if lvl is None:
            continue
        if s.get("type") == "SSL_SWEEP" and last < lvl:
            return _res("rr_liq_inval_acceptance_after_sweep", True,
                        f"SSL sweep at {lvl} followed by acceptance (close {last} below level)")
        if s.get("type") == "BSL_SWEEP" and last > lvl:
            return _res("rr_liq_inval_acceptance_after_sweep", True,
                        f"BSL sweep at {lvl} followed by acceptance (close {last} above level)")
    return _res("rr_liq_inval_acceptance_after_sweep", False, "Sweeps rejected (or none) — reversal intact")


_EVALUATORS = {
    "tc_inval_choch": _tc_choch,
    "tc_inval_regime_shift": _tc_regime,
    "tc_liq_inval_opposing_sweep": _tc_opp_sweep,
    "pc_inval_structure_break": _pc_struct_break,
    "pc_inval_regime_shift": _pc_regime,
    "pc_inval_deep_pullback": _pc_deep_pullback,
    "pc_liq_inval_opposing_sweep": _pc_opp_sweep,
    "rr_inval_regime_change": _rr_regime,
    "rr_inval_breakout": _rr_breakout,
    "rr_liq_inval_acceptance_after_sweep": _rr_acceptance,
}
