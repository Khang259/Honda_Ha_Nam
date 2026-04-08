from __future__ import annotations

from dataclasses import dataclass
import os


def _get_env_str(key: str, default: str) -> str:
    v = os.getenv(key)
    return v if v is not None and v != "" else default


def _get_env_int(key: str, default: int) -> int:
    v = os.getenv(key)
    if v is None or v == "":
        return default
    try:
        return int(v)
    except ValueError:
        return default


def _get_env_float(key: str, default: float) -> float:
    v = os.getenv(key)
    if v is None or v == "":
        return default
    try:
        return float(v)
    except ValueError:
        return default


@dataclass(frozen=True)
class APISettings:
    AREA_NAME: str = _get_env_str("AREA_NAME", "AE5")
    
    # MongoDB
    MongoDB_URL: str = _get_env_str("MongoDB_URL", "mongodb://localhost:27017/")
    MongoDB_DB: str = _get_env_str("MongoDB_DB", "HONDA_HN")
    
    # Uvicorn runtime
    API_SERVER_HOST: str = _get_env_str("API_SERVER_HOST", "0.0.0.0")
    API_SERVER_PORT: int = _get_env_int("API_SERVER_PORT", 5000)
    API_LOG_LEVEL: str = _get_env_str("API_LOG_LEVEL", "info")


settings = APISettings()

