import threading
from utils.setup_log import setup_logger
from ui.gui_monitor import GUIMonitor

logger = setup_logger("ui_thread", "logs/ui_thread/log")

class UIT:
    def __init__(
        self,
        api_client=None,
        state_manager=None,
        validate_pairs=None,
        shutdown_callback=None,
        camera_manager=None,
        camera_api_client=None,
        pairs_by_zone=None,
        cameras_config=None,
        camera_zones=None,
        rtsp_ae5=None,
        rtsp_ae6=None,
        rtsp_5l=None,
        rtsp_6l=None,
        rtsp_af=None,
    ):
        self.api_client = api_client
        self.state_manager = state_manager
        self.validate_pairs = validate_pairs
        self.shutdown_callback = shutdown_callback
        self.camera_manager = camera_manager
        self.camera_api_client = camera_api_client
        self.pairs_by_zone = pairs_by_zone
        self.cameras_config = cameras_config
        self.camera_zones = camera_zones
        self.rtsp_ae5 = rtsp_ae5 or set()
        self.rtsp_ae6 = rtsp_ae6 or set()
        self.rtsp_5l = rtsp_5l or set()
        self.rtsp_6l = rtsp_6l or set()
        self.rtsp_af = rtsp_af or set()
        self.gui = None
        self.thread = None
    
    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=False, name="UIT")
        self.thread.start()
        logger.info("UIT thread started")
    
    def stop(self):
        """Gracefully stop GUI."""
        if self.gui and self.gui.window:
            try:
                self.gui.window.quit()
                self.gui.window.destroy()
                logger.info("GUI stopped")
            except Exception as e:
                logger.error(f"Error stopping GUI: {e}")
    
    def run(self):
        self.gui = GUIMonitor(
            api_client=self.api_client,
            state_manager=self.state_manager,
            validate_pairs=self.validate_pairs,
            shutdown_callback=self.shutdown_callback,
            camera_manager=self.camera_manager,
            camera_api_client=self.camera_api_client,
            pairs_by_zone=self.pairs_by_zone,
            cameras_config=self.cameras_config,
            camera_zones=self.camera_zones,
            rtsp_ae5=self.rtsp_ae5,
            rtsp_ae6=self.rtsp_ae6,
            rtsp_5l=self.rtsp_5l,
            rtsp_6l=self.rtsp_6l,
            rtsp_af=self.rtsp_af,
        )
        self.gui.run()