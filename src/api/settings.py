from __future__ import annotations

from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Cấu hình từ .env — product chỉ cần đổi giá trị env, không sửa code.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- MongoDB connection (app) ---
    # Dev mặc định: 3 node local replica set
    MongoDB_URL: str = Field(
        default=(
            "mongodb://localhost:27018,localhost:27019,localhost:27020/"
            "?replicaSet=rs0"
        ),
        description="Mongo connection string (product: thay host/IP + replicaSet)",
    )
    MongoDB_DB: str = Field(
        default="HONDA_HN",
        description="Tên database",
    )

    # --- Replica topology (dùng khi cấu hình rs.initiate / rs.reconfig; không bắt buộc lúc chạy app) ---
    # 1 máy preferred primary (master ưu tiên) + các máy voting còn lại.
    # Product: chỉ thay IP/host, giữ cùng tên biến.
    MONGO_REPLICA_SET: str = Field(default="rs0", description="Tên replica set")
    MONGO_PREFERRED_PRIMARY: str = Field(
        default="localhost:27018",
        description="Host:port ưu tiên làm primary (priority cao hơn)",
    )
    MONGO_VOTING_MEMBERS: str = Field(
        default="localhost:27018,localhost:27019,localhost:27020",
        description=(
            "CSV host:port member có votes (gồm preferred primary). "
            "Product 4 máy: 1 preferred primary + 3 voting — chỉ đổi IP trong env."
        ),
    )

    # Pairing / start events — product đổi tên qua env, không sửa code
    START_EVENTS_COLLECTION: str = Field(
        default="start_events_test",
        description="Tên collection start events (product: START_EVENTS_COLLECTION=start_events)",
    )

    # Uvicorn runtime
    AI_SERVER_HOST: str = Field(default="0.0.0.0", description="Host for the AI server")
    AI_SERVER_PORT: int = Field(default=5000, description="Port for the AI server")
    AI_LOG_LEVEL: str = Field(default="info", description="Log level for the AI server")

    # Worker Configuration
    WORKER_ID: str = Field(..., description="Unique worker ID")
    WORKER_IP: str = Field(..., description="Worker IP address")
    HEARTBEAT_INTERVAL: int = Field(default=10, description="Heartbeat interval in seconds")
    HEARTBEAT_TIMEOUT: int = Field(default=30, description="Heartbeat timeout in seconds")

    def mongo_voting_member_list(self) -> List[str]:
        """Parse MONGO_VOTING_MEMBERS CSV → list host:port."""
        return [m.strip() for m in self.MONGO_VOTING_MEMBERS.split(",") if m.strip()]


settings = Settings()
