# File: ui/camera_api_client.py
"""
HTTP client wrapper để UI gọi camera control API.
"""
import httpx
from utils.setup_log import setup_logger

logger = setup_logger("camera_api_client", "logs/camera_api_client/log")


class CameraAPIClient:
    """Client để gọi camera control API từ UI."""
    
    def __init__(self, api_url: str):
        """
        Args:
            api_url: Base URL của API server (e.g., "http://192.168.1.30:5001")
        """
        self.api_url = api_url.rstrip('/')
        self.client = httpx.Client(timeout=10.0)
        logger.info(f"CameraAPIClient initialized with URL: {self.api_url}")
    
    def start_all_cameras(self):
        """Start all cameras."""
        try:
            resp = self.client.post(f"{self.api_url}/cameras/start-all")
            result = resp.json()
            if result.get("success"):
                logger.info("All cameras started successfully")
            else:
                logger.error(f"Failed to start cameras: {result.get('error')}")
            return result
        except Exception as e:
            logger.error(f"Error starting all cameras: {e}")
            return {"error": str(e), "success": False}
    
    def stop_all_cameras(self):
        """Stop all cameras."""
        try:
            resp = self.client.post(f"{self.api_url}/cameras/stop-all")
            result = resp.json()
            if result.get("success"):
                logger.info("All cameras stopped successfully")
            else:
                logger.error(f"Failed to stop cameras: {result.get('error')}")
            return result
        except Exception as e:
            logger.error(f"Error stopping all cameras: {e}")
            return {"error": str(e), "success": False}
    
    def set_zone_enabled(self, zone: str, enabled: bool):
        """
        Enable/disable cameras by zone.
        
        Args:
            zone: Zone name (e.g., "AE5", "AE6")
            enabled: True to enable, False to disable
        """
        action = "start" if enabled else "stop"
        endpoint = f"{self.api_url}/cameras/{zone}/{action}-all"
        try:
            resp = self.client.post(endpoint)
            result = resp.json()
            if result.get("success"):
                logger.info(f"Zone {zone} cameras {'enabled' if enabled else 'disabled'}")
            else:
                logger.error(f"Failed to set zone {zone}: {result.get('error')}")
            return result
        except Exception as e:
            logger.error(f"Error setting zone {zone}: {e}")
            return {"error": str(e), "success": False}
    
    def toggle_node_flag(self, node_id: str):
        """
        Toggle flag của node_id.
        
        Args:
            node_id: Node ID (e.g., "start_10000060")
        """
        try:
            resp = self.client.post(f"{self.api_url}/cameras/flag/{node_id}")
            result = resp.json()
            if result.get("success"):
                logger.info(f"Toggled flag for {node_id}: {result.get('flag')}")
            else:
                logger.error(f"Failed to toggle flag {node_id}: {result.get('error')}")
            return result
        except Exception as e:
            logger.error(f"Error toggling flag {node_id}: {e}")
            return {"error": str(e), "success": False}
    
    def get_zone_status(self, zone: str):
        """
        Get current status of all nodes in zone.
        
        Args:
            zone: Zone name (e.g., "AE5", "AE6")
        
        Returns:
            Dict with nodes state/flag
        """
        try:
            resp = self.client.get(f"{self.api_url}/cameras/{zone}")
            return resp.json()
        except Exception as e:
            logger.error(f"Error getting zone {zone} status: {e}")
            return {"error": str(e), "success": False}
    
    def close(self):
        """Close HTTP client."""
        self.client.close()
        logger.info("CameraAPIClient closed")
