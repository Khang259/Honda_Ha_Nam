import os
import re
import threading
import time
from datetime import datetime, timedelta
import numpy as np
import cv2

from shared.setup_log import setup_logger


logger = setup_logger("snapshot_manager", "logs/snapshot_manager/log")


def _sanitize_for_filename(value: str) -> str:
    """
    Chuẩn hoá chuỗi để dùng làm tên file an toàn trên Windows.
    - Thay khoảng trắng bằng '_'
    - Loại bỏ / thay thế các ký tự không hợp lệ (:, \, /, ...)
    """
    value = value.replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9._-]", "_", value)


class SnapshotManager:
    def __init__(self, snapshot_dir: str = "snapshots", quality: int = 95):
        """
        Quản lý lưu trữ và thao tác với snapshots.

        Args:
            snapshot_dir: Thư mục lưu ảnh snapshot.
            quality: Chất lượng JPEG (0-100).
        """
        self.snapshot_dir = snapshot_dir
        self.quality = max(0, min(int(quality), 100))
        self._lock = threading.Lock()
        self._frames = {}  # {node_id: frame}
        self._count = 0

        os.makedirs(self.snapshot_dir, exist_ok=True)
        logger.info(
            f"SnapshotManager initialized - dir: {self.snapshot_dir}, quality: {self.quality}"
        )

    def update_frame(self, node_id: str, frame):
        """
        Cập nhật frame mới nhất cho một node_id.

        Args:
            node_id: Mã điểm (start_xxx / end_xxx).
            frame: numpy array (BGR).
        """
        if frame is None:
            return

        with self._lock:
            # Lưu bản copy để tránh bị mutate ở nơi khác
            self._frames[node_id] = frame.copy()

    def save_pair_snapshots(self, start_point: str, end_point: str, order_id: str):
        """
        Lưu snapshots cho start_point và end_point.

        Format tên file: {orderId}_{node_id}_{timestamp}.jpg

        Returns:
            tuple(start_path, end_path)
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        start_path = None
        end_path = None

        # Lấy frame hiện tại, nếu thiếu thì retry một vài lần với delay ngắn
        with self._lock:
            start_frame = self._frames.get(start_point)
            end_frame = self._frames.get(end_point)

        if start_frame is None or end_frame is None:
            retry_attempts = 3
            retry_delay = 0.2  # giây
            for _ in range(retry_attempts):
                time.sleep(retry_delay)
                with self._lock:
                    if start_frame is None:
                        start_frame = self._frames.get(start_point)
                    if end_frame is None:
                        end_frame = self._frames.get(end_point)
                if start_frame is not None and end_frame is not None:
                    break

        try:
            safe_order_id = _sanitize_for_filename(order_id)

            if start_frame is not None and end_frame is not None:
                combined = np.hstack([start_frame, end_frame])
                filename = f"{safe_order_id}_{start_point}-{end_point}_{timestamp}.jpg"
                path = os.path.join(self.snapshot_dir, filename)
                ok = cv2.imwrite(path, combined, [int(cv2.IMWRITE_JPEG_QUALITY), self.quality])
                if ok:
                    with self._lock:
                        self._count += 1
                    logger.info(f"Saved pair snapshot: {filename}")
                    return path, path
                else:
                    logger.error(f"Failed to write snapshot: {path}")
            else:
                if start_frame is not None and end_frame is None:
                    filename = f"{safe_order_id}_{start_point}-{end_point}_{timestamp}.jpg"
                    path = os.path.join(self.snapshot_dir, filename)
                    ok = cv2.imwrite(path, start_frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.quality])
                    if ok:
                        with self._lock:
                            self._count += 1
                        logger.info(f"Saved pair snapshot: {filename}")
                        return path, None
                    else:
                        logger.error(f"Failed to write snapshot: {path}")
                if end_frame is None:
                    logger.warning(f"No frame for end_point: {end_point}")
        except Exception as e:
            logger.error(f"Error saving snapshots for orderId={order_id}: {e}")

        return None, None
    def get_snapshot_count(self) -> int:
        """Trả về tổng số snapshots đã lưu (đếm từ lúc khởi tạo)."""
        with self._lock:
            return self._count

    def cleanup_old_snapshots(self, keep_days: int = 7):
        """
        Xoá snapshots cũ hơn keep_days ngày.

        Args:
            keep_days: Số ngày giữ lại.
        """
        try:
            cutoff = datetime.now() - timedelta(days=keep_days)
            removed = 0

            for filename in os.listdir(self.snapshot_dir):
                if not filename.lower().endswith(".jpg"):
                    continue

                path = os.path.join(self.snapshot_dir, filename)
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(path))
                    if mtime < cutoff:
                        os.remove(path)
                        removed += 1
                except Exception as e:
                    logger.warning(f"Failed to check/remove file {path}: {e}")

            if removed > 0:
                logger.info(f"Cleanup old snapshots: removed {removed} files older than {keep_days} days")
        except Exception as e:
            logger.error(f"Error during cleanup_old_snapshots: {e}")
