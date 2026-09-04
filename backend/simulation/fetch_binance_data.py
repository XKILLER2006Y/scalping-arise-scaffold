import ccxt
import pandas as pd
import logging
import os
import time
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("binance-fetcher")

def fetch_binance_paxg(days: int = 30):
    """
    Fetches real historical 1-minute OHLCV data for PAXG/USDT (Crypto Gold)
    from Binance. This gives us high-fidelity factual data.
    """
    exchange = ccxt.binance()
    symbol = "PAXG/USDT"
    timeframe = "1m"
    
    logger.info(f"Fetching {days} days of {timeframe} data for {symbol} from Binance...")
    
    # Calculate start time
    end_time = exchange.milliseconds()
    start_time = end_time - (days * 24 * 60 * 60 * 1000)
    
    all_ohlcv = []
    current_start = start_time
    
    while current_start < end_time:
        try:
            # Binance limits to 1000 candles per request
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=current_start, limit=1000)
            if not ohlcv:
                break
            
            all_ohlcv.extend(ohlcv)
            current_start = ohlcv[-1][0] + 60000 # advance by 1 minute
            
            logger.info(f"Fetched {len(all_ohlcv)} candles so far. Current date: {datetime.fromtimestamp(current_start/1000)}")
            time.sleep(0.5) # rate limit protection
            
        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            time.sleep(5)
            
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('datetime', inplace=True)
    
    os.makedirs("data", exist_ok=True)
    filepath = "data/real_paxg_1m.csv"
    df.to_csv(filepath)
    logger.info(f"Successfully saved {len(df)} factual historical records to {filepath}")
    
    return filepath

if __name__ == "__main__":
    # Fetch just 7 days first for speed, can expand later
    fetch_binance_paxg(days=7)
