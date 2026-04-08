from __future__ import annotations
from pydantic import BaseSettings, SettingsConfigDict, Field

class Settings(BaseSettings):
    #Load environment variables from .env file
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    AREA_NAME: str = Field(default="AE5")
    
    # MongoDB
    MongoDB_URL: str = Field(default="mongodb://localhost:27017/")
    MongoDB_DB: str = Field(default="HONDA_HN")
    
    # Uvicorn runtime
    API_SERVER_HOST: str = Field(default="0.0.0.0")
    API_SERVER_PORT: int = Field(default=5000)
    API_LOG_LEVEL: str = Field(default="info")


settings = Settings()

