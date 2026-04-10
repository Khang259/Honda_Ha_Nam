import time
import threading
from collections import deque
import requests
from config import END_POINT_EMPTY
from utils.setup_log import setup_logger
from utils.data import payload_sent_ICS, payload_sent_ICS_empty, payload_sent_ICS_double


logger = setup_logger("pair_manager", "logs/pair_manager/log")


class PairManager:

    def __init__(
        self,
        ics_url,
        state_manager,
        validate_pairs,
        snapshot_manager=None,
    ):
        """
        Args:
            ics_url: URL của ICS server
            state_manager: Instance của StateManager
            validate_pairs: Set các cặp valid
            timeout: Timeout cho POST request (seconds)
            snapshot_manager: Instance của SnapshotManager (hoặc None nếu tắt snapshot)
        """
        self.ics_url = ics_url
        self.state_manager = state_manager
        self.validate_pairs = validate_pairs
        self.snapshot_manager = snapshot_manager
        self.running = False
        self.thread = None
        self.pending_empty_queue = []  # list[(start_empty, deadline)]
        logger.info("PairManager initialized")
    
    def make_pairs(self):
        """
        Trả về các normal pairs + payloads.
        - Empty start (len(pair) == 1) được đưa vào pending_empty_queue để xử lý double/timeout.
        - Với normal pair (len(pair) == 2): mỗi start chỉ được bắt với 1 end trong 1 vòng chạy,
          thứ tự ưu tiên theo FIFO của danh sách start đang ready.
        """
        payloads = []
        pairs = []

        now = time.time()

        # 1) Xử lý các cặp empty (len == 1): chỉ dùng để đẩy vào hàng chờ pending_empty_queue
        for pair in self.validate_pairs:
            if len(pair) == 1:
                start_empty = pair[0]

                if start_empty in self.state_manager.ready_start_list:
                    # kiểm tra chưa có trong queue để tránh trùng
                    if not any(start_empty == item[0] for item in self.pending_empty_queue):
                        deadline = now + 15  # chờ tối đa 15s
                        self.pending_empty_queue.append((start_empty, deadline))
                # không gửi payload ngay

        # 2) Xử lý normal pairs (len == 2) theo thứ tự FIFO start
        used_starts = set()
        used_ends = set()

        # Tạo queue FIFO từ các start đang ready ở thời điểm hiện tại
        start_queue = deque(self.state_manager.ready_start_list)

        while start_queue:
            start_point = start_queue.popleft()

            # Bỏ qua nếu start này đã được dùng trong vòng make_pairs hiện tại
            if start_point in used_starts:
                continue

            # Tìm một end phù hợp cho start này trong validate_pairs
            candidate_end = None
            for pair in self.validate_pairs:
                if len(pair) != 2:
                    continue
                s, e = pair
                if s != start_point:
                    continue
                if e in self.state_manager.ready_end_list and e not in used_ends:
                    candidate_end = e
                    break

            if candidate_end is None:
                # Start này hiện chưa có end phù hợp đang ready, bỏ qua trong vòng này
                continue

            payload = payload_sent_ICS(start_point, candidate_end)
            payloads.append(payload)
            pairs.append((start_point, candidate_end))

            used_starts.add(start_point)
            used_ends.add(candidate_end)

        return pairs, payloads
    
    def post_to_ics(self, payload):
        """
        POST request đến ICS server.
        
        Returns:
            bool: True nếu thành công, False nếu thất bại
        """
        try:
            response = requests.post(
                self.ics_url, 
                json=payload
            )
            
            if response.status_code != 200:
                logger.error(f"POST failed - status: {response.status_code}")
                return False
            
            response_data = response.json()
            
            if response_data.get("code") == 1000:
                logger.debug(f"POST successful for orderId: {payload.get('orderId')}")
                return True
            else:
                logger.error(f"ICS error response: {response_data}")
                return False
        except Exception as e:
            logger.error(f"POST error: {e}")
            return False
    
    def start(self):
        """Khởi động pair processing thread."""
        self.running = True
        self.thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="PairManager"
        )
        self.thread.start()
        #logger.info("PairManager thread started")
    
    def stop(self):
        """Dừng pair processing thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        #logger.info("PairManager thread stopped")
    
    def _run(self):
        logger.info("PairManager processing loop started")

        while self.running:
            try:
                self.state_manager.process_starts()
                self.state_manager.process_ends()

                pairs, payloads = self.make_pairs()
                now = time.time()

                # 1) Ghép double tasks theo FIFO empty queue
                normal_idx = 0
                while normal_idx < len(pairs) and self.pending_empty_queue: #Kiểm tra có normal VA empty để gửi lệnh 
                    start_empty, deadline = self.pending_empty_queue[0]  #Unpack start_empty và deadline từ queue

                    # Hết hạn 15s -> gửi empty (không consume normal pair)
                    if now > deadline:
                        end_empty = END_POINT_EMPTY #End point của empty car
                        payload_empty = payload_sent_ICS_empty(start_empty, end_empty)
                        success = self.post_to_ics(payload_empty)
                        order_id = payload_empty.get("orderId")

                        if success:
                            if self.snapshot_manager is not None:
                                self.snapshot_manager.save_pair_snapshots(
                                    start_empty, end_empty, order_id
                            )
                            #TODO: Check the start_empty is work well with logic status == 23 or 3 just for reset flag with empty car
                            self.state_manager.set_pair_used(start_empty, end_empty, order_id, empty_car=True) #TODO: check var empty_car still avail
                        else:
                            logger.error(
                                f"Failed to post empty pair ({start_empty}, {end_empty}) with orderId: {order_id}"
                            )

                        self.pending_empty_queue.pop(0)  # Loại bỏ khỏi queue sau khi gửi lệnh để tránh trùng 
                        continue

                    # Còn hạn -> ghép với normal pair tiếp theo
                    start_point, end_point = pairs[normal_idx]
                    end_empty = END_POINT_EMPTY
                    payload_double = payload_sent_ICS_double(
                        start_point, end_point,
                        start_empty, end_empty
                    )

                    success = self.post_to_ics(payload_double)
                    order_id = payload_double.get("orderId")
                    logger.debug(f"Post double pair ({start_point}, {end_point}) + ({start_empty}, {end_empty}) with orderId: {order_id}")

                    if success:
                        if self.snapshot_manager is not None:
                            self.snapshot_manager.save_pair_snapshots(
                                start_point, end_point, order_id
                            )
                        self.state_manager.set_pair_used(start_point, end_point, order_id, empty_car=False)
                        self.state_manager.set_pair_used(start_empty, end_empty, order_id, empty_car=True)
                    else:
                        logger.error(
                            f"Failed to post double pair "
                            f"({start_point}, {end_point}) + ({start_empty}, {end_empty}) "
                            f"with orderId: {order_id}"
                        )

                    self.pending_empty_queue.pop(0)
                    normal_idx += 1

                # 2) Các normal pairs còn lại -> gửi single như cũ
                for pair, payload in zip(pairs[normal_idx:], payloads[normal_idx:]):
                    start_point, end_point = pair
                    order_id = payload.get("orderId")

                    success = self.post_to_ics(payload)
                    logger.debug(f"Post pair ({start_point}, {end_point}) with orderId: {order_id}")
                    if success:
                        if self.snapshot_manager is not None:
                            self.snapshot_manager.save_pair_snapshots(
                                start_point, end_point, order_id
                            )
                        self.state_manager.set_pair_used(start_point, end_point, order_id, empty_car=False)
                    else:
                        logger.error(
                            f"Failed to post pair ({start_point}, {end_point}) "
                            f"with orderId: {order_id}"
                        )

                # 3) Không còn normal pair -> flush các empty đã timeout
                while self.pending_empty_queue:
                    start_empty, deadline = self.pending_empty_queue[0]
                    if now <= deadline:
                        break

                    end_empty = END_POINT_EMPTY
                    payload_empty = payload_sent_ICS_empty(start_empty, end_empty)
                    success = self.post_to_ics(payload_empty)
                    order_id = payload_empty.get("orderId")
                    logger.debug(f"Post empty pair ({start_empty}, {end_empty}) with orderId: {order_id}")

                    if success:
                        if self.snapshot_manager is not None:
                            self.snapshot_manager.save_pair_snapshots(
                                start_empty, end_empty, order_id
                            )
                        self.state_manager.set_pair_used(start_empty, end_empty, order_id, empty_car=True)
                    else:
                        logger.error(
                            f"Failed to post empty pair ({start_empty}, {end_empty}) with orderId: {order_id}"
                        )

                    self.pending_empty_queue.pop(0)

                time.sleep(1)

            except Exception as e:
                logger.error(f"Error in pair processing loop: {e}", exc_info=True)
                time.sleep(1)