# File: state_manager.py
import time
import threading
from collections import defaultdict
from shared.setup_log import setup_logger
    
logger = setup_logger("state_manager", "logs/state_manager/log")

class StateManager:
    def __init__(self, validate_pairs=None):
        if validate_pairs is None:
            validate_pairs = set()
        self._lock = threading.Lock()
        self.points = defaultdict(lambda: {"state": False, "time": time.time(), "flag": False, "frame": None})
        self.ready_start_list = set() ### Change this to queue for FIFO
        self.ready_end_list = set() ### Change this to queue for FIFO
        # node_id -> cameraId (Mongo) để publish start_events kèm cameraId
        self.node_camera_by_node_id = {}
        self.pair_mapping = {}
        # {orderId: [(start_point, end_point, empty_car), ...]}
        # - Single task: 1 tuple
        # - Double task: 2 tuples (normal + empty) sharing same orderId
        self.order_mapping = {}
        self.validate_pairs = validate_pairs

    def get_state_nodes(self, node_id, state, frame=None, camera_id=None):
        with self._lock:
            if camera_id is not None:
                try:
                    self.node_camera_by_node_id[node_id] = int(camera_id)
                except (TypeError, ValueError):
                    pass
            current = self.points[node_id]
            old_state = current["state"]
            current["state"] = state

            if old_state != state:
                if node_id.startswith("start_"):
                    if state:
                        current["time"] = time.time()
                    else:
                        current["time"] = time.time()
                        self.ready_start_list.discard(node_id)

                elif node_id.startswith("end_"):
                    if not state:
                        current["time"] = time.time()
                    else:
                        current["time"] = time.time()
                        self.ready_end_list.discard(node_id)
    
    def process_starts(self):
        current_time = time.time()
        with self._lock:
            for node_id, data in list(self.points.items()):
                if not node_id.startswith("start_"):
                    continue

                if data["state"]:
                    if not data["flag"]:
                        existed_time = current_time - data["time"]
                        if existed_time > 30:
                            if node_id not in self.ready_start_list:
                                self.ready_start_list.add(node_id)

    def process_ends(self):
        current_time = time.time()
        with self._lock:
            for node_id, data in list(self.points.items()):
                if not node_id.startswith("end_"):
                    continue
                if not data["state"]:
                    if not data["flag"]:
                        existed_time = current_time - data["time"]
                        if existed_time > 30:
                            if node_id not in self.ready_end_list:
                                self.ready_end_list.add(node_id)

            
            #This business logic is used to reset the flag for 2 points start and end
            #The reset mechanism is depends on the state of the end point
            #else: #Không cần reset flag cho end point vì đã được reset bởi webhook
                # if data["flag"]:
                #     existed_time = current_time - data["time"]
                    
                #     if existed_time > 30:
                #         self.ready_end_list.discard(node_id)
                #         start_point = self.pair_mapping.get(node_id)
                        
                #         if start_point:
                #             self.ready_start_list.discard(start_point)
                #             self.points[node_id]["flag"] = False
                #             self.points[start_point]["flag"] = False
                #             del self.pair_mapping[node_id]
                #         else:
                #             logger.warning(
                #                 f"No start_point found in pair_mapping for {node_id}")
                #             self.points[node_id]["flag"] = False

    def set_pair_used(self, start_point, end_point, order_id, empty_car=False): #Empty car để check lệnh dôi
        """Move pair từ ready sang used, set flags."""
        with self._lock:
            self.points[start_point]["flag"] = True
            self.points[end_point]["flag"] = True

            self.ready_start_list.discard(start_point)
            self.ready_end_list.discard(end_point)

            self.pair_mapping[end_point] = start_point
            pairs = self.order_mapping.setdefault(order_id, [])
            pairs.append((start_point, end_point, empty_car))

    def snapshot_ready_ends(self):
        """Copy ready_end_list (thread-safe) cho pairing loop."""
        with self._lock:
            return list(self.ready_end_list)

    def snapshot_ready_starts(self):
        with self._lock:
            return list(self.ready_start_list)

    def get_camera_id_for_node(self, node_id: str):
        with self._lock:
            return self.node_camera_by_node_id.get(node_id)

    def is_node_flagged(self, node_id: str) -> bool:
        with self._lock:
            return bool(self.points[node_id]["flag"])