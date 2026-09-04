import random
import time

def generate_mbp_ticks(num_ticks: int = 1000, start_price: float = 2650.0):
    """Generates synthetic Market-By-Price (MBP) ticks."""
    ticks = []
    current_time = int(time.time() * 1000)
    current_bid = start_price
    
    for _ in range(num_ticks):
        current_time += random.randint(1, 50)  # 1-50ms between ticks
        
        # Random walk
        drift = random.choice([-0.1, 0.0, 0.1])
        current_bid += drift
        current_ask = current_bid + 0.2  # 20 cent spread
        
        # Generate bid tick
        ticks.append({
            "timestamp_ms": current_time,
            "price": round(current_bid, 2),
            "volume": random.randint(10, 100),
            "is_bid": True
        })
        
        # Generate ask tick
        ticks.append({
            "timestamp_ms": current_time + random.randint(1, 5),
            "price": round(current_ask, 2),
            "volume": random.randint(10, 100),
            "is_bid": False
        })
        
    return ticks
