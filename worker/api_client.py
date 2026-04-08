# File: worker/api_client.py
"""
HTTP client để AI worker giao tiếp với API server.
"""
import httpx
import time
from typing import Dict, Any, Optional, List
from utils.setup_log import setup_logger
from settings import settings

logger = setup_logger("api_client", "logs/api_client/log")

class APIClient:
    """HTTP client wrapper để gọi API server."""
    
    def __init__(self, timeout: float = 5.0):
        """
        Args:
            timeout: Timeout cho mỗi request (seconds)
        """
        self.api_url = settings.API_URL.rstrip('/')
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)
        logger.info(f"APIClient initialized with URL: {settings.API_URL}")
    
    def post_detection(self, cam_id: str, node_id: str, detected: bool, coverage: Optional[float] = None) -> bool:
        """
        Gửi detection result lên API server.
        
        Args:
            cam_id: Camera ID
            node_id: Node ID (start_* hoặc end_*)
            detected: True nếu phát hiện object, False nếu không
            coverage: Optional coverage percentage
            
        Returns:
            bool: True nếu thành công, False nếu thất bại
        """
        try:
            response = self.client.post(
                f"{self.api_url}/detections",
                json={
                    "cam_id": cam_id,
                    "node_id": node_id,
                    "detected": detected,
                    "coverage": coverage
                }
            )
            
            if response.status_code == 200:
                return True
            else:
                logger.error(f"POST detection failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"POST detection error: {e}")
            return False
    
    def get_points_state(self) -> Optional[Dict[str, Any]]:
        """
        Lấy toàn bộ points state từ API server.
        
        Returns:
            Dict với format: {"node_id": {"state": bool, "time": float, "flag": bool}}
            Hoặc None nếu request thất bại
        """
        try:
            response = self.client.get(f"{self.api_url}/state/points")
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    return data.get("points", {})
            
            logger.error(f"GET points state failed: {response.status_code}")
            return None
            
        except Exception as e:
            logger.error(f"GET points state error: {e}")
            return None
    
    def get_ready_lists(self) -> Optional[Dict[str, List[str]]]:
        """
        Lấy ready_start_list và ready_end_list từ API server.
        
        Returns:
            Dict với format: {"ready_start_list": [...], "ready_end_list": [...]}
            Hoặc None nếu request thất bại
        """
        logger.warning("GET /state/ready-lists was removed; returning empty lists")
        return {"ready_start_list": set(), "ready_end_list": set()}
    
    def health_check(self) -> bool:
        """
        Kiểm tra API server có sẵn sàng không.
        
        Returns:
            bool: True nếu API server OK, False nếu không
        """
        try:
            response = self.client.get(f"{self.api_url}/health")
            return response.status_code == 200
        except Exception:
            return False
    
    def wait_for_api(self, max_retries: int = 30, retry_delay: float = 2.0) -> bool:
        """
        Chờ API server sẵn sàng.
        
        Args:
            max_retries: Số lần retry tối đa
            retry_delay: Delay giữa các lần retry (seconds)
            
        Returns:
            bool: True nếu API server sẵn sàng, False nếu timeout
        """
        logger.info(f"Waiting for API server at {self.api_url}...")
        
        for i in range(max_retries):
            if self.health_check():
                logger.info("API server is ready")
                return True
            
            logger.debug(f"API server not ready, retry {i+1}/{max_retries}...")
            time.sleep(retry_delay)
        
        logger.error(f"API server not ready after {max_retries} retries")
        return False
    
    def close(self):
        """Đóng HTTP client."""
        self.client.close()
