import pandas as pd
import numpy as np
import logging
import os
import joblib
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("xgboost-trainer")

def train_on_real_data():
    filepath = "data/real_paxg_1m.csv"
    if not os.path.exists(filepath):
        logger.error(f"Data file not found at {filepath}")
        return
        
    logger.info("Loading factual historical data...")
    df = pd.read_csv(filepath)
    df.set_index('datetime', inplace=True)
    
    logger.info("Computing advanced factual features...")
    # Feature 1: Returns & Volatility
    df['return'] = df['close'].pct_change()
    df['log_return'] = np.log(df['close'] / df['close'].shift(1))
    df['volatility_14'] = df['log_return'].rolling(14).std()
    
    # Feature 2: Garman-Klass Volatility (incorporates High/Low/Open/Close for better variance estimation)
    df['gk_vol'] = np.sqrt(0.5 * np.log(df['high'] / df['low'])**2 - (2 * np.log(2) - 1) * np.log(df['close'] / df['open'])**2).rolling(14).mean()
    
    # Feature 3: Pseudo-Order Flow Imbalance (CVD Approximation)
    # If close is closer to high, buyers dominated. If closer to low, sellers dominated.
    df['buy_pressure'] = (df['close'] - df['low']) / (df['high'] - df['low'] + 1e-8)
    df['ofi_proxy'] = (df['buy_pressure'] - 0.5) * df['volume']
    df['cvd'] = df['ofi_proxy'].rolling(14).sum()
    
    # Feature 4: RSI (Relative Strength Index)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-8)
    df['rsi_14'] = 100 - (100 / (1 + rs))
    
    # Feature 5: Momentum & Moving Average Distances
    df['sma_9'] = df['close'].rolling(9).mean()
    df['sma_21'] = df['close'].rolling(21).mean()
    df['dist_sma9'] = (df['close'] - df['sma_9']) / df['sma_9']
    df['dist_sma21'] = (df['close'] - df['sma_21']) / df['sma_21']
    
    # Target: 1 if price is higher 5 minutes from now, else 0
    df['future_5m_close'] = df['close'].shift(-5)
    df['target'] = (df['future_5m_close'] > df['close']).astype(int)
    
    # Drop NaNs created by rolling and shifting
    df.dropna(inplace=True)
    
    features = [
        'return', 'log_return', 'volatility_14', 'gk_vol', 
        'buy_pressure', 'cvd', 'rsi_14', 'dist_sma9', 'dist_sma21', 'volume'
    ]
    X = df[features]
    y = df['target']
    
    logger.info(f"Training on {len(X)} real historical rows...")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)
    
    model = XGBClassifier(
        n_estimators=100, 
        learning_rate=0.05, 
        max_depth=4, 
        eval_metric='logloss',
        random_state=42
    )
    
    model.fit(X_train, y_train)
    
    logger.info("Testing model on out-of-sample data...")
    preds = model.predict(X_test)
    probs = model.predict_proba(X_test)[:, 1] # Probability of Class 1 (Price UP)
    
    acc = accuracy_score(y_test, preds)
    logger.info(f"Overall Accuracy: {acc*100:.2f}%")
    
    # Evaluate High Confidence Threshold (Quant Edge)
    threshold = 0.55
    high_conf_long_indices = probs > threshold
    high_conf_short_indices = probs < (1 - threshold)
    
    long_acc = accuracy_score(y_test[high_conf_long_indices], preds[high_conf_long_indices]) if sum(high_conf_long_indices) > 0 else 0
    short_acc = accuracy_score(y_test[high_conf_short_indices], preds[high_conf_short_indices]) if sum(high_conf_short_indices) > 0 else 0
    
    logger.info(f"Number of High Confidence LONG signals (> {threshold*100}%): {sum(high_conf_long_indices)}")
    if sum(high_conf_long_indices) > 0:
        logger.info(f"High Confidence LONG Accuracy: {long_acc*100:.2f}%")
        
    logger.info(f"Number of High Confidence SHORT signals (< {(1-threshold)*100}%): {sum(high_conf_short_indices)}")
    if sum(high_conf_short_indices) > 0:
        logger.info(f"High Confidence SHORT Accuracy: {short_acc*100:.2f}%")
    
    os.makedirs("models", exist_ok=True)
    model_path = "models/real_xgb_model.pkl"
    joblib.dump(model, model_path)
    logger.info(f"Factual model saved to {model_path}")

if __name__ == "__main__":
    train_on_real_data()
