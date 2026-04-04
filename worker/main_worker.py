# File: worker/main_worker.py
"""
Entry point cho AI worker - GPU inference headless.
Không khởi tạo StateManager, sử dụng API client để giao tiếp với API server.
"""
import signal
import sys
import time
import os
import threading
import uvicorn
from config import (
    CAMERAS,
    INFERENCE_MAX_QUEUE_SIZE,
    INFERENCE_MAX_BATCH_SIZE,
    INFERENCE_BATCH_TIMEOUT,
    INFERENCE_NUM_STREAMS,
    MODEL_PATH,
    ENABLE_SNAPSHOTS,
    SNAPSHOT_DIR,
    SNAPSHOT_QUALITY,
)
from core.camera_manager import CameraManager
from core.inference_engine import InferenceEngine
from core.snapshot_manager import SnapshotManager
from worker.api_client import APIClient
from utils.setup_log import setup_logger
from settings import settings

logger = setup_logger("worker_main", "logs/worker_main/log")

API_URL = os.getenv(
    "API_URL",
    f"http://{settings.API_SERVER_HOST}:{settings.API_SERVER_PORT}",
)

class WorkerManager:
    """Manager để quản lý AI worker."""
    
    def __init__(self):
        self.components = {}
        self.running = False
        self.api_client = None
        self.camera_service_thread = None
    
    def initialize(self):
        """Khởi tạo components cho AI worker."""
        logger.info("Initializing AI worker components...")
        
        self.api_client = APIClient()
        logger.info(f"API_URL: {API_URL}")
        
        if not self.api_client.wait_for_api(max_retries=30, retry_delay=2.0):
            logger.error("Cannot connect to API server, exiting...")
            sys.exit(1)
        
        snapshot_manager = None
        if ENABLE_SNAPSHOTS:
            snapshot_manager = SnapshotManager(
                snapshot_dir=SNAPSHOT_DIR,
                quality=SNAPSHOT_QUALITY,
            )
        
        inference_engine = InferenceEngine(
            model_path=MODEL_PATH,
            max_queue_size=INFERENCE_MAX_QUEUE_SIZE,
            max_batch_size=INFERENCE_MAX_BATCH_SIZE,
            batch_timeout=INFERENCE_BATCH_TIMEOUT,
            num_streams=INFERENCE_NUM_STREAMS
        )
        inference_engine.start()
        
        camera_zones = [c.get("area_name", c.get("zone")) for c in CAMERAS]
        camera_manager = CameraManager(
            CAMERAS,
            None,  # Không dùng state_manager
            inference_engine,
            snapshot_manager=snapshot_manager,
            camera_zones=camera_zones,
            api_client=self.api_client,  # Truyền api_client thay vì state_manager
        )
        camera_manager.start()
        
        # Set reference cho camera_service
        from worker import camera_service
        camera_service.camera_manager_ref = camera_manager
        
        # Start camera service HTTP server trong thread riêng
        self.camera_service_thread = threading.Thread(
            target=self._run_camera_service,
            daemon=True,
            name="CameraService"
        )
        self.camera_service_thread.start()
        logger.info("Camera service HTTP server started on port 5002")
        
        self.components = {
            'inference_engine': inference_engine,
            'camera_manager': camera_manager,
            'snapshot_manager': snapshot_manager,
            'api_client': self.api_client
        }
        
        self.running = True
        logger.info("AI worker components initialized")
    
    def _run_camera_service(self):
        """Run camera service HTTP server."""
        from worker.camera_service import app as camera_app
        try:
            # Port 5002 để tránh conflict với API server (5001)
            uvicorn.run(
                camera_app,
                host="0.0.0.0",
                port=5002,
                log_level="warning",
                access_log=False
            )
        except Exception as e:
            logger.error(f"Camera service error: {e}")
    
    def run(self):
        """Keep worker running."""
        logger.info("AI worker is running...")
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
    
    def shutdown(self):
        """Graceful shutdown."""
        if not self.running:
            return
        
        logger.info("STARTING AI WORKER SHUTDOWN")
        self.running = False
        
        if 'inference_engine' in self.components:
            self.components['inference_engine'].stop()
        
        if 'camera_manager' in self.components:
            self.components['camera_manager'].stop()
        
        if 'api_client' in self.components:
            self.components['api_client'].close()
        
        logger.info("AI WORKER SHUTDOWN COMPLETED")
        sys.exit(0)

def main():
    worker_manager = WorkerManager()
    
    def signal_handler(sig, frame):
        """Handle Ctrl+C signal."""
        worker_manager.shutdown()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    worker_manager.initialize()
    worker_manager.run()

if __name__ == "__main__":
    main()
