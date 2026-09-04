"""Centralized configuration. Single source of truth for thresholds."""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[2]  # backend/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_BACKEND_DIR / ".env", extra="ignore")
    app_name: str = "Scalping Arise"
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:3000"]
    sca_api_key: str = ""  # optional guard; env SCA_API_KEY. Empty = open demo mode.

    # --- Market data ---
    twelve_data_api_key: str = ""
    twelve_data_base_url: str = "https://api.twelvedata.com"
    default_symbol: str = "XAU/USD"
    cache_ttl_seconds: int = 15
    freshness_max_age_seconds: int = 120
    # expected candle interval per timeframe (seconds)
    tf_interval_seconds: dict[str, int] = {"1m": 60, "5m": 300, "15m": 900}

    # --- Phase 4 extension: volatility (ATR% = ATR / close) ---
    # Tunable for XAU/USD sessions. Env-overridable: VOL_LOW, etc.
    vol_low_max: float = 0.0008
    vol_normal_max: float = 0.0020
    vol_high_max: float = 0.0040
    # >= vol_high_max -> EXTREME_VOLATILITY

    # --- Indicator defaults ---
    ema_fast: int = 9
    ema_slow: int = 21
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_period: int = 14
    bb_period: int = 20
    bb_std: float = 2.0


settings = Settings()
