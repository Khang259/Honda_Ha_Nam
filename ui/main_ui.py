# File: ui/main_ui.py
"""
Entry point cho UI monitor - chạy local để monitoring system.
"""
import signal
import sys
import os
from config import VALIDATE_PAIRS, VALIDATE_PAIRS_BY_ZONE, CAMERAS
from core.pair_manager import get_validate_pairs
from ui.ui_thread import UIT
from worker.api_client import APIClient
from ui.camera_api_client import CameraAPIClient
from utils.setup_log import setup_logger
from settings import settings

logger = setup_logger("ui_main", "logs/ui_main/log")
# Default API URL is built from host/port in `settings.py`.
# If you still provide `API_URL` via environment, it will override this value.
API_URL = os.getenv(
    "API_URL",
    f"http://{settings.API_SERVER_HOST}:{settings.API_SERVER_PORT}",
)

class UIManager:
    """Manager để quản lý UI monitor."""
    
    def __init__(self):
        self.ui = None
        self.api_client = None
        self.camera_api_client = None
    
    def initialize(self):
        """Khởi tạo UI components."""
        logger.info("Initializing UI monitor...")
        
        self.api_client = APIClient()
        logger.info(f"API_URL: {API_URL}")
        
        if not self.api_client.wait_for_api(max_retries=10, retry_delay=2.0):
            logger.error("Cannot connect to API server, exiting...")
            sys.exit(1)
        
        # Tạo camera API client
        self.camera_api_client = CameraAPIClient(API_URL)
        
        validate_pairs = get_validate_pairs(VALIDATE_PAIRS)
        camera_zones = [c.get("area_name", c.get("zone")) for c in CAMERAS]
        
        self.ui = UIT(
            api_client=self.api_client,
            camera_api_client=self.camera_api_client,
            validate_pairs=validate_pairs,
            shutdown_callback=self.shutdown,
            pairs_by_zone=VALIDATE_PAIRS_BY_ZONE,
            cameras_config=CAMERAS,
            camera_zones=camera_zones,
        )
        
        logger.info("UI monitor initialized")
    
    def start(self):
        """Start UI."""
        if self.ui:
            self.ui.start()
    
    def shutdown(self):
        """Graceful shutdown."""
        logger.info("UI MONITOR SHUTDOWN")
        if self.camera_api_client:
            self.camera_api_client.close()
        if self.api_client:
            self.api_client.close()
        sys.exit(0)

def main():
    ui_manager = UIManager()
    
    def signal_handler(sig, frame):
        """Handle Ctrl+C signal."""
        ui_manager.shutdown()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    ui_manager.initialize()
    ui_manager.start()

if __name__ == "__main__":
    main()
