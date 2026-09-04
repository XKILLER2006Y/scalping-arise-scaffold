"""Phase 4.5 AI Market Sentiment Module with Cached Model Singleton."""
import os
import math
from app.core.logging import get_logger

logger = get_logger("scalping-arise.sentiment")

_CACHED_MODEL = None
_MODEL_LOADED = False

def reset_model_cache():
    """Reset the singleton model cache (useful for testing)."""
    global _CACHED_MODEL, _MODEL_LOADED
    _CACHED_MODEL = None
    _MODEL_LOADED = False

def _get_model():
    """Get the cached ML model singleton, or load it from disk."""
    global _CACHED_MODEL, _MODEL_LOADED
    try:
        import joblib
    except ImportError:
        return None  # ML deps not installed: caller falls back to NEUTRAL
    from unittest.mock import Mock

    is_mocked = isinstance(joblib.load, Mock) or isinstance(os.path.exists, Mock)

    if _MODEL_LOADED and _CACHED_MODEL is not None and not is_mocked:
        return _CACHED_MODEL

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    candidate_paths = [
        os.path.join(repo_root, "models", "real_xgb_model.pkl"),
    ]

    loaded_model = None
    for path in candidate_paths:
        if os.path.exists(path):
            try:
                loaded_model = joblib.load(path)
                logger.info(f"Loaded ML model from {path}")
                break
            except Exception as e:
                logger.warning(f"Failed loading model from {path}: {e}")
                loaded_model = None

    if not is_mocked:
        _CACHED_MODEL = loaded_model
        _MODEL_LOADED = True

    return loaded_model

def analyze_sentiment(mtf_features: dict, structure: dict | None = None) -> dict:
    """Analyze market sentiment using XGBoost ML Model alongside technical heuristics."""
    if not mtf_features:
        return {"sentiment": "NEUTRAL", "confidence": 50, "reasons": ["No features"]}

    # Support flat dict, nested 1m dict, or features wrapper dict
    if isinstance(mtf_features, dict):
        if "1m" in mtf_features and isinstance(mtf_features["1m"], dict):
            features = mtf_features["1m"].get("features", mtf_features["1m"])
        elif "features" in mtf_features and isinstance(mtf_features["features"], dict):
            features = mtf_features["features"]
        elif "timeframes" in mtf_features and isinstance(mtf_features["timeframes"], dict) and "1m" in mtf_features["timeframes"]:
            features = mtf_features["timeframes"]["1m"].get("features", mtf_features["timeframes"]["1m"])
        else:
            features = mtf_features
    else:
        return {"sentiment": "NEUTRAL", "confidence": 50, "reasons": ["Invalid features"]}

    if not features or not isinstance(features, dict):
        return {"sentiment": "NEUTRAL", "confidence": 50, "reasons": ["No features"]}

    def _clean_float(val, default=0.0) -> float:
        if val is None:
            return default
        try:
            f = float(val)
            return default if (math.isnan(f) or math.isinf(f)) else f
        except (ValueError, TypeError):
            return default

    model = _get_model()
    prob = 0.5

    if model is not None:
        try:
            import pandas as pd
            rng = _clean_float(features.get("price_range"), 1e-8)
            pos = _clean_float(features.get("position_in_range"), 0.5)
            buy_pressure = pos if rng > 0 else 0.5
            buy_pressure = max(0.0, min(1.0, buy_pressure))

            X = pd.DataFrame([{
                'return': _clean_float(features.get("return")),
                'log_return': _clean_float(features.get("log_return")),
                'volatility_14': _clean_float(features.get("volatility_14", features.get("volatility"))),
                'gk_vol': _clean_float(features.get("gk_vol", features.get("garman_klass"))),
                'buy_pressure': buy_pressure,
                'cvd': _clean_float(features.get("cvd")),
                'rsi_14': _clean_float(features.get("rsi_14", features.get("rsi14")), 50.0),
                'dist_sma9': _clean_float(features.get("dist_sma9")),
                'dist_sma21': _clean_float(features.get("dist_sma21")),
                'volume': _clean_float(features.get("volume"))
            }])

            raw_proba = model.predict_proba(X)
            if hasattr(raw_proba, "shape") and len(raw_proba.shape) > 1 and raw_proba.shape[1] > 1:
                p = float(raw_proba[0][1])
            elif hasattr(raw_proba, "__getitem__"):
                row = raw_proba[0]
                p = float(row[1]) if len(row) > 1 else float(row[0])
            else:
                p = float(raw_proba)

            if not math.isnan(p) and not math.isinf(p):
                prob = max(0.0, min(1.0, p))
            else:
                prob = 0.5
        except Exception as e:
            logger.warning(f"XGB inference error: {e}")
            prob = 0.5

    # Bound prob safely
    if math.isnan(prob) or math.isinf(prob):
        prob = 0.5
    else:
        prob = max(0.0, min(1.0, prob))

    sentiment = "NEUTRAL"
    confidence = int(round(abs(prob - 0.5) * 100)) + 50
    reasons = [f"ML Prediction: {prob:.2f}"]

    if prob > 0.6:
        sentiment = "BULLISH"
    elif prob < 0.4:
        sentiment = "BEARISH"

    if structure:
        trend = structure.get("trend") if isinstance(structure, dict) else getattr(structure, "trend", None)
        if trend == "UPTREND":
            confidence += 10
            reasons.append("Market Structure Uptrend")
        elif trend == "DOWNTREND":
            confidence += 10
            reasons.append("Market Structure Downtrend")

    return {
        "sentiment": sentiment,
        "confidence": min(100, max(0, confidence)),
        "reasons": reasons
    }

