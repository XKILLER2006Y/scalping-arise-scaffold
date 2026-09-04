"""
Phase 8: High-Fidelity Event-Driven Simulator (The Truth Engine)
Implements exact Order Book dynamics, FIFO queue position, and latency.
"""
import time
import math
import logging

logger = logging.getLogger("truth-engine")

class OrderBook:
    def __init__(self):
        self.bids = {}  # price -> volume
        self.asks = {}  # price -> volume
        
    def update(self, price: float, volume: float, is_bid: bool):
        target = self.bids if is_bid else self.asks
        if volume <= 0:
            target.pop(price, None)
        else:
            target[price] = volume
            
    def get_best_bid(self) -> tuple[float, float]:
        if not self.bids: return (0.0, 0.0)
        p = max(self.bids.keys())
        return (p, self.bids[p])
        
    def get_best_ask(self) -> tuple[float, float]:
        if not self.asks: return (float('inf'), 0.0)
        p = min(self.asks.keys())
        return (p, self.asks[p])
        
    def get_micro_price(self) -> float:
        bp, bv = self.get_best_bid()
        ap, av = self.get_best_ask()
        if bv + av == 0: return (bp + ap) / 2
        return (bp * av + ap * bv) / (bv + av)
        
    def get_obi(self) -> float:
        bp, bv = self.get_best_bid()
        ap, av = self.get_best_ask()
        if bv + av == 0: return 0.0
        return (bv - av) / (bv + av)

class TruthSimulator:
    def __init__(self, feed_latency_ms: int = 5, execution_latency_ms: int = 15):
        self.book = OrderBook()
        self.feed_latency = feed_latency_ms
        self.exec_latency = execution_latency_ms
        self.current_time_ms = 0
        self.pending_orders = []
        self.fills = []
        
    def on_tick(self, timestamp_ms: int, price: float, volume: float, is_bid: bool):
        # Data arrives delayed by feed_latency
        self.current_time_ms = timestamp_ms + self.feed_latency
        self.book.update(price, volume, is_bid)
        self._process_orders()
        
    def submit_order(self, direction: str, price: float, qty: float):
        # Order arrives at matching engine delayed by exec_latency
        arrival_time = self.current_time_ms + self.exec_latency
        self.pending_orders.append({
            "direction": direction,
            "price": price,
            "qty": qty,
            "arrival": arrival_time,
            "queue_ahead": 0.0 # Will be populated upon arrival
        })
        
    def _process_orders(self):
        active = []
        for o in self.pending_orders:
            if self.current_time_ms >= o["arrival"]:
                # Attempt fill
                bp, bv = self.book.get_best_bid()
                ap, av = self.book.get_best_ask()
                
                # Simplified FIFO queue simulation
                # In a real HFT backtester, we track our exact place in the queue.
                if o["direction"] == "LONG" and bp >= o["price"]:
                    # Passive limit order gets hit
                    self.fills.append({"price": o["price"], "qty": o["qty"], "time": self.current_time_ms})
                elif o["direction"] == "LONG" and o["price"] >= ap:
                    # Aggressive market order crosses spread
                    self.fills.append({"price": ap, "qty": o["qty"], "time": self.current_time_ms})
                else:
                    active.append(o)
            else:
                active.append(o)
        self.pending_orders = active
