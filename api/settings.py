from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

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
    AI_SERVER_HOST: str = Field(default="0.0.0.0")
    AI_SERVER_PORT: int = Field(default=5000)
    AI_LOG_LEVEL: str = Field(default="info")


settings = Settings()

