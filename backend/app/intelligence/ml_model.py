"""Legacy ML model stub — real inference is in sentiment.py via models/real_xgb_model.pkl.

This module exists only for backward compatibility with any code that
imports `ml_model`.  It does NOT train or write pickles on import.
"""
import os
import math

# No import-side-effect model creation.  The old code trained a random model
# on `import` and wrote it to disk — that is removed.

MODEL_PATH = os.path.join(os.path.dirname(__file__), "xgb_model.pkl")


class XGBoostSentimentModel:
    """Stub that always returns NEUTRAL.  Real predictions go through
    sentiment.analyze_sentiment → models/real_xgb_model.pkl."""

    def __init__(self):
        self.model = None

    def predict(self, features: dict) -> dict:
        return {"sentiment": "NEUTRAL", "confidence": 0,
                "reasons": ["Legacy stub — use sentiment.analyze_sentiment()"]}


ml_model = XGBoostSentimentModel()
