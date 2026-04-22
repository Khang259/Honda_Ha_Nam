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
    # AREA_NAME: str = Field(default="AE5")
    
    # MongoDB
    MongoDB_URL: str = Field(default="mongodb://localhost:27017/", description="MongoDB URL")
    MongoDB_DB: str = Field(default="HONDA_HN", description="MongoDB database name")
    
    # Uvicorn runtime
    AI_SERVER_HOST: str = Field(default="0.0.0.0",description="Host for the AI server")
    AI_SERVER_PORT: int = Field(default=5000,description="Port for the AI server")
    AI_LOG_LEVEL: str = Field(default="info",description="Log level for the AI server")
    
    # Worker Configuration
    WORKER_ID: str = Field(default="w1", description="Unique worker ID")
    WORKER_IP: str = Field(default="127.0.0.1", description="Worker IP address")
    HEARTBEAT_INTERVAL: int = Field(default=10, description="Heartbeat interval in seconds")
    HEARTBEAT_TIMEOUT: int = Field(default=30, description="Heartbeat timeout in seconds")


settings = Settings()

