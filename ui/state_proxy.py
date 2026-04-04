# File: ui/state_proxy.py
"""
State proxy để UI có thể poll state từ API server.
"""
import time
from collections import defaultdict
from utils.setup_log import setup_logger

logger = setup_logger("state_proxy", "logs/state_proxy/log")

class StateProxy:
    """
    Proxy object giả lập StateManager để UI có thể đọc state từ API.
    Poll API định kỳ và cache local.
    """
    
    def __init__(self, api_client):
        """
        Args:
            api_client: APIClient instance
        """
        self.api_client = api_client
        self.points = defaultdict(lambda: {"state": False, "time": time.time(), "flag": False, "frame": None})
        self.ready_start_list = set()
        self.ready_end_list = set()
        self.last_update = 0
        self.update_interval = 0.5  # Poll mỗi 500ms
    
    def refresh(self):
        """Poll state từ API server."""
        now = time.time()
        if now - self.last_update < self.update_interval:
            return
        
        try:
            points_data = self.api_client.get_points_state()
            if points_data:
                for node_id, data in points_data.items():
                    self.points[node_id].update(data)
            
            ready_lists = self.api_client.get_ready_lists()
            if ready_lists:
                self.ready_start_list = ready_lists.get("ready_start_list", set())
                self.ready_end_list = ready_lists.get("ready_end_list", set())
            
            self.last_update = now
        except Exception as e:
            logger.error(f"Error refreshing state from API: {e}")
