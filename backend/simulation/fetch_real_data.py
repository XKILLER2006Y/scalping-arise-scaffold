import yfinance as yf
import pandas as pd
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("data-fetcher")

def fetch_gold_data(days: int = 7):
    """
    Fetches real historical 1-minute data for Gold Futures (GC=F) 
    using Yahoo Finance.
    """
    ticker = "GC=F"
    logger.info(f"Fetching last {days} days of 1-minute tick data for {ticker}...")
    
    # yfinance only allows 1m data for the last 7 days max
    data = yf.download(ticker, period=f"{days}d", interval="1m")
    
    if data.empty:
        logger.error("Failed to fetch data.")
        return None
        
    logger.info(f"Successfully fetched {len(data)} real historical ticks.")
    
    # Save to csv
    os.makedirs("data", exist_ok=True)
    filepath = "data/real_gold_1m.csv"
    data.to_csv(filepath)
    logger.info(f"Saved real historical data to {filepath}")
    
    return filepath

if __name__ == "__main__":
    fetch_gold_data()
