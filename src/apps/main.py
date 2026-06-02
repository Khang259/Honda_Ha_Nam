# File: apps/main.py (entry uvicorn)
"""
Entry point cho API server - quản lý state và nhận requests từ worker/UI.
"""
import signal
import sys
import uvicorn

from api.settings import settings
from api import ai_server
from shared.setup_log import setup_logger

logger = setup_logger("ai_main", "logs/ai_main/log")

class AIManager:
    """Manager để quản lý AI server và state."""
    
    def __init__(self):
        self.running = False
    
    def initialize(self):
        self.running = True
        logger.info("AI server runtime initialized")
    
    def shutdown(self):
        """Graceful shutdown."""
        if not self.running:
            return
        
        logger.info("STARTING AI SERVER SHUTDOWN")
        self.running = False

        logger.info("AI SERVER SHUTDOWN COMPLETED")
        sys.exit(0)

def main():
    ai_manager = AIManager()
    
    def signal_handler(sig, frame):
        """Handle Ctrl+C signal."""
        ai_manager.shutdown()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    ai_manager.initialize()
    
    logger.info(f"Starting AI server on {settings.AI_SERVER_HOST}:{settings.AI_SERVER_PORT}")
    uvicorn.run(
        ai_server.app,
        host=settings.AI_SERVER_HOST,
        port=settings.AI_SERVER_PORT,
        log_level=settings.AI_LOG_LEVEL
    )

if __name__ == "__main__":
    main()
