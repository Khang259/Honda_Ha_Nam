from pathlib import Path
from typing import Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """
    Load cấu hình từ file `.env` trong cùng thư mục với `settings.py`.
    Dùng pydantic-settings để tránh phụ thuộc vào việc `python-dotenv`.
    """

    API_SERVER_HOST: str = "0.0.0.0"
    API_SERVER_PORT: int = 5000
    API_LOG_LEVEL: str = "info"
    API_URL: Optional[str] = None
    WORKER_INTERNAL_URL: str = "http://localhost:5002"  # Worker camera service endpoint
    MongoDB_URL: Optional[str] = None
    MongoDB_DB: str = "HONDA_HN"

    @model_validator(mode="after")
    def build_api_url(self):
        if not self.API_URL:
            object.__setattr__(self, "API_URL", f"http://{self.API_SERVER_HOST}:{self.API_SERVER_PORT}")
        return self

    model_config = SettingsConfigDict(
        env_file=Path(__file__).with_name(".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = AppSettings()