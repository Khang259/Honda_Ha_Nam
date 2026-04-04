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
    # Backend BE base URL (where /node_id/{area} lives)
    BE_BASE_URL: str = _get_env_str("BE_BASE_URL", "http://localhost:8000")
    AREA_NAME: str = _get_env_str("AREA_NAME", "AE5")

    # HTTP fetch timeouts/caching
    BE_TIMEOUT_S: float = _get_env_float("BE_TIMEOUT_S", 5.0)
    CONFIG_CACHE_TTL_S: float = _get_env_float("CONFIG_CACHE_TTL_S", 10.0)

    # Uvicorn runtime
    API_SERVER_HOST: str = _get_env_str("API_SERVER_HOST", "0.0.0.0")
    API_SERVER_PORT: int = _get_env_int("API_SERVER_PORT", 5000)
    API_LOG_LEVEL: str = _get_env_str("API_LOG_LEVEL", "info")


settings = APISettings()

