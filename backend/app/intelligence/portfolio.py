"""Portfolio-level guards: the "five independent 1% trades that are really one 5% trade" killer.

Per-trade sizing is not risk management. This gate caps CONCURRENT correlated
exposure before a new position opens: same-direction stacking on one symbol and
total open risk across the book.
"""
from __future__ import annotations

MAX_SAME_DIR_PER_SYMBOL = 2
MAX_OPEN_POSITIONS = 5
MAX_BOOK_RISK_PCT = 3.0  # sum of risk_money across open positions, % of equity


def check(positions: list[dict], direction: str | None, symbol: str = "XAU/USD",
          risk_money: float = 0.0, equity: float = 10000.0) -> dict:
    """positions: open position dicts with direction/symbol/risk_money keys."""
    if not direction:
        return {"allowed": False, "reason": "no direction"}
    same = [p for p in positions
            if p.get("direction") == direction and p.get("symbol", "XAU/USD") == symbol]
    if len(same) >= MAX_SAME_DIR_PER_SYMBOL:
        return {"allowed": False,
                "reason": f"correlation cap: {len(same)} {direction} {symbol} already open (max {MAX_SAME_DIR_PER_SYMBOL})"}
    if len(positions) >= MAX_OPEN_POSITIONS:
        return {"allowed": False, "reason": f"book full: {len(positions)} open (max {MAX_OPEN_POSITIONS})"}
    book_risk = sum(float(p.get("risk_money", 0.0) or 0.0) for p in positions) + risk_money
    book_pct = book_risk / equity * 100 if equity else 0.0
    if book_pct > MAX_BOOK_RISK_PCT:
        return {"allowed": False,
                "reason": f"book risk {book_pct:.2f}% exceeds {MAX_BOOK_RISK_PCT}% cap"}
    return {"allowed": True, "reason": None, "book_risk_pct": round(book_pct, 2)}
