# File: api/main_api.py
"""
Entry point cho API server - quản lý state và nhận requests từ worker/UI.
"""
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load ai-n-s-2-p-docker-db/.env before api.settings (os.getenv / BE_BASE_URL).
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import uvicorn

from config import API_SERVER_HOST, API_SERVER_PORT, API_LOG_LEVEL
from api import api_server
from utils.setup_log import setup_logger

logger = setup_logger("api_main", "logs/api_main/log")

class APIManager:
    """Manager để quản lý API server và state."""
    
    def __init__(self):
        self.running = False
    
    def initialize(self):
        # Startup is handled by FastAPI lifespan (see api/app_factory.py).
        self.running = True
        logger.info("API server runtime initialized")
    
    def shutdown(self):
        """Graceful shutdown."""
        if not self.running:
            return
        
        logger.info("STARTING API SERVER SHUTDOWN")
        self.running = False

        # Shutdown is handled by FastAPI lifespan.
        logger.info("API SERVER SHUTDOWN COMPLETED")
        sys.exit(0)

def main():
    api_manager = APIManager()
    
    def signal_handler(sig, frame):
        """Handle Ctrl+C signal."""
        api_manager.shutdown()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    api_manager.initialize()
    
    logger.info(f"Starting API server on {API_SERVER_HOST}:{API_SERVER_PORT}")
    uvicorn.run(
        api_server.app,
        host=API_SERVER_HOST,
        port=API_SERVER_PORT,
        log_level=API_LOG_LEVEL
    )

if __name__ == "__main__":
    main()
