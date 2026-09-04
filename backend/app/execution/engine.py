"""Phase 11 Broker Execution Engine (Paper Trading)"""
import math
import threading
import time

# Gold: 1 standard lot = 100 troy ounces
CONTRACT_OZ = 100.0

class PaperBroker:
    def __init__(self, initial_balance=10000.0):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.high_water_mark = initial_balance
        self.daily_start_balance = initial_balance
        self.open_positions = []
        self.trade_history = []
        self.is_halted = False
        self.halt_reason = ""
        self._lock = threading.Lock()

    def get_portfolio(self) -> dict:
        with self._lock:
            drawdown_pct = (self.high_water_mark - self.balance) / self.high_water_mark * 100
            daily_loss_pct = (self.daily_start_balance - self.balance) / self.daily_start_balance * 100
            return {
                "balance": round(self.balance, 2),
                "high_water_mark": round(self.high_water_mark, 2),
                "drawdown_pct": round(drawdown_pct, 2),
                "daily_loss_pct": round(daily_loss_pct, 2),
                "is_halted": self.is_halted,
                "halt_reason": self.halt_reason,
                "open_positions": list(self.open_positions),
                "history_count": len(self.trade_history),
            }

    def execute_trade(self, plan: dict):
        with self._lock:
            if not plan:
                return {"status": "skipped", "reason": "No valid trade plan"}

            # Check feasible flag
            feasible = plan.get("feasible", True)
            if not feasible:
                return {"status": "skipped", "reason": plan.get("reason") or "No valid trade plan"}

            # Check action
            action = plan.get("action")
            if not action and "signal" in plan and isinstance(plan["signal"], dict):
                action = plan["signal"].get("action")
            if action == "NO_TRADE":
                return {"status": "skipped", "reason": plan.get("reason") or "No valid trade plan"}

            # Check direction
            direction = plan.get("direction")
            if not direction and "signal" in plan and isinstance(plan["signal"], dict):
                direction = plan["signal"].get("direction")
            if not direction or direction not in ("LONG", "SHORT"):
                return {"status": "skipped", "reason": "No valid trade plan"}

            if self.is_halted:
                return {"status": "rejected", "reason": self.halt_reason}

            # Global human kill switch (app/core/halt.py) — covers paper AND live paths.
            try:
                from app.core.halt import get_halt
                h = get_halt()
                if h.get("halted"):
                    return {"status": "rejected",
                            "reason": f"HALTED by operator: {h.get('reason') or 'no reason given'}"}
            except Exception:
                pass

            # Circuit Breaker Check
            drawdown_pct = (self.high_water_mark - self.balance) / self.high_water_mark * 100
            daily_loss_pct = (self.daily_start_balance - self.balance) / self.daily_start_balance * 100

            if drawdown_pct >= 8.0:
                self.is_halted = True
                self.halt_reason = f"Prop-Firm Circuit Breaker: Max Trailing Drawdown ({drawdown_pct:.2f}%) exceeded 8% limit."
                return {"status": "rejected", "reason": self.halt_reason}

            if daily_loss_pct >= 4.0:
                self.is_halted = True
                self.halt_reason = f"Prop-Firm Circuit Breaker: Daily Loss Limit ({daily_loss_pct:.2f}%) exceeded 4% limit."
                return {"status": "rejected", "reason": self.halt_reason}

            # Normalize values
            entry_val = plan.get("entry_price") if plan.get("entry_price") is not None else plan.get("entry")
            if entry_val is None:
                return {"status": "skipped", "reason": "No valid trade plan"}
            try:
                entry_price = float(entry_val)
                if math.isnan(entry_price) or math.isinf(entry_price) or entry_price <= 0:
                    return {"status": "skipped", "reason": "Invalid entry price"}
            except (ValueError, TypeError):
                return {"status": "skipped", "reason": "Invalid entry price"}

            size_val = plan.get("position_size") if plan.get("position_size") is not None else plan.get("lots")
            if size_val is None:
                size_val = 0.1
            try:
                size = float(size_val)
                if math.isnan(size) or math.isinf(size) or size <= 0:
                    return {"status": "skipped", "reason": "Invalid lot size"}
            except (ValueError, TypeError):
                return {"status": "skipped", "reason": "Invalid lot size"}

            sl = plan.get("stop_loss") if plan.get("stop_loss") is not None else plan.get("stop")
            tp = plan.get("take_profit_1") if plan.get("take_profit_1") is not None else plan.get("take_profit")

            try:
                sl_val = float(sl) if sl is not None and not math.isnan(float(sl)) and not math.isinf(float(sl)) else None
            except (ValueError, TypeError):
                sl_val = None

            try:
                tp_val = float(tp) if tp is not None and not math.isnan(float(tp)) and not math.isinf(float(tp)) else None
            except (ValueError, TypeError):
                tp_val = None

            position = {
                "id": int(time.time_ns()),
                "direction": direction,
                "entry": float(entry_price),
                "sl": sl_val,
                "tp": tp_val,
                "size": float(size),
                "status": "OPEN",
                "timestamp": int(time.time()),
            }
            self.open_positions.append(position)
            return {"status": "filled", "position": position}

    def on_tick(self, tick):
        """Monitors open positions against the latest tick price for SL/TP exit triggers."""
        with self._lock:
            if not self.open_positions or tick is None:
                return []

            closed = []
            remaining = []
            try:
                h = float(tick.high)
                l = float(tick.low)
                c = float(tick.close)
                if any(math.isnan(x) or math.isinf(x) for x in (h, l, c)):
                    return []
            except (ValueError, TypeError, AttributeError):
                return []

            for p in self.open_positions:
                hit_sl = False
                hit_tp = False
                exit_px = c

                if p["direction"] == "LONG":
                    if p.get("sl") is not None and l <= p["sl"]:
                        hit_sl = True
                        exit_px = p["sl"]
                    elif p.get("tp") is not None and h >= p["tp"]:
                        hit_tp = True
                        exit_px = p["tp"]
                elif p["direction"] == "SHORT":
                    if p.get("sl") is not None and h >= p["sl"]:
                        hit_sl = True
                        exit_px = p["sl"]
                    elif p.get("tp") is not None and l <= p["tp"]:
                        hit_tp = True
                        exit_px = p["tp"]

                if hit_sl or hit_tp:
                    pnl = (exit_px - p["entry"]) * p["size"] * CONTRACT_OZ if p["direction"] == "LONG" else (p["entry"] - exit_px) * p["size"] * CONTRACT_OZ
                    p["exit"] = exit_px
                    p["pnl"] = round(pnl, 2)
                    p["status"] = "CLOSED"
                    p["exit_reason"] = "SL" if hit_sl else "TP"
                    self.balance += pnl
                    self.trade_history.append(p)
                    closed.append(p)
                else:
                    remaining.append(p)

            self.open_positions = remaining
            if self.balance > self.high_water_mark:
                self.high_water_mark = self.balance
            return closed

    def close_all(self, current_price: float):
        with self._lock:
            try:
                cp = float(current_price)
                if math.isnan(cp) or math.isinf(cp) or cp <= 0:
                    return {"closed": [], "new_balance": round(self.balance, 2)}
            except (ValueError, TypeError):
                return {"closed": [], "new_balance": round(self.balance, 2)}

            closed = []
            for p in self.open_positions:
                if p["direction"] == "LONG":
                    pnl = (cp - p["entry"]) * p["size"] * CONTRACT_OZ
                else:
                    pnl = (p["entry"] - cp) * p["size"] * CONTRACT_OZ

                p["exit"] = cp
                p["pnl"] = round(pnl, 2)
                p["status"] = "CLOSED"
                self.balance += pnl
                self.trade_history.append(p)
                closed.append(p)

            self.open_positions = []
            if self.balance > self.high_water_mark:
                self.high_water_mark = self.balance

            return {"closed": closed, "new_balance": round(self.balance, 2)}

broker = PaperBroker()
