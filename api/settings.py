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
    #AREA_NAME: str = Field(default="AE5", description="Default area for reload endpoint")
    
    # MongoDB
    MongoDB_URL: str = Field(..., description="MongoDB URL")
    MongoDB_DB: str = Field(..., description="MongoDB database name")
    
    # Uvicorn runtime
    AI_SERVER_HOST: str = Field(...,description="Host for the AI server")
    AI_SERVER_PORT: int = Field(...,description="Port for the AI server")
    AI_LOG_LEVEL: str = Field(...,description="Log level for the AI server")
    
    # Worker Configuration
    WORKER_ID: str = Field(..., description="Unique worker ID")
    WORKER_IP: str = Field(..., description="Worker IP address")
    HEARTBEAT_INTERVAL: int = Field(..., description="Heartbeat interval in seconds")
    HEARTBEAT_TIMEOUT: int = Field(..., description="Heartbeat timeout in seconds")


settings = Settings()

