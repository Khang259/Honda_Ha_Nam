"""
Shared database connection and utilities
MongoDB connection using Motor (async driver)
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Optional
from utils.setup_log import setup_logger

logger = setup_logger("database", "logs/database/log")

class Database:
    client: Optional[AsyncIOMotorClient] = None
    database: Optional[AsyncIOMotorDatabase] = None

db = Database()

async def connect_to_mongo(mongodb_url: str, mongodb_database: str):
    """Kết nối MongoDB khi khởi động runtime."""
    try:
        logger.info(f"Connecting to MongoDB: {mongodb_url}")
        db.client = AsyncIOMotorClient(mongodb_url)
        db.database = db.client[mongodb_database]
        await db.client.admin.command('ping')
        logger.info(f"Connected to MongoDB: {mongodb_database}")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise

async def close_mongo_connection():
    """Đóng kết nối khi shutdown."""
    if db.client:
        db.client.close()
        logger.info("Disconnected from MongoDB")

def get_database() -> Optional[AsyncIOMotorDatabase]:
    """Get database instance."""
    return db.database

def get_collection(collection_name: str):
    """Get collection instance."""
    if db.database is None:
        raise RuntimeError("Database not connected. Call connect_to_mongo() first.")

    return db.database[collection_name]
