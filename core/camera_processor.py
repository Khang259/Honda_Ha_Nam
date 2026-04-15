# File: camera_processor.py
import cv2
import threading
import time
import queue
from core.detection import has_object_in_roi
from core.state_manager import StateManager
from core.gpu_video_decoder import GPUVideoDecoder
from utils.setup_log import setup_logger

logger = setup_logger("camera_processor", "logs/camera_processor/log")


class CameraProcessor(threading.Thread):
    def __init__(
        self,
        rtsp,
        rois,
        state_manager,
        inference_engine,
        result_queue,
        cam_id,
        snapshot_manager=None,
        enabled_ref=None,
        camera_index=0,
        latest_frames_ref=None,
        api_client=None,
    ):
        super().__init__()
        self.rtsp = rtsp
        self.rois = rois
        self.state_manager = state_manager
        self.inference_engine = inference_engine
        self.result_queue = result_queue
        self.cam_id = cam_id
        self.snapshot_manager = snapshot_manager
        self.enabled_ref = enabled_ref if enabled_ref is not None else []
        self.camera_index = camera_index
        self.latest_frames_ref = latest_frames_ref if latest_frames_ref is not None else {}
        self.api_client = api_client  # API client cho worker mode
        self.running = True
        self.window_name = f"Camera {rtsp.split('/')[-1]}"
        
        # Cache detections for streaming API
        self.latest_detections = None
        self._detections_lock = threading.Lock()

    #Hàm kiểm tra trạng thái camera(threading) đã được bật hay chưa?
    def _is_enabled(self):
        if self.camera_index < len(self.enabled_ref):
            return self.enabled_ref[self.camera_index]
        return True

    def run(self):
        cap = None

        while self.running:
            if not self._is_enabled():
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass
                    cap = None
                time.sleep(1)
                continue

            if cap is None or not cap.isOpened():
                cap = GPUVideoDecoder(self.rtsp)
                if not cap.isOpened():
                    logger.error(f"Cannot open RTSP: {self.rtsp}")
                    time.sleep(2)
                    continue
                logger.info(f"Waiting for first frame from {self.rtsp}...")
                #Hết timeout kill process FFmpeg và giải phóng tài nguyên
                if not cap.wait_ready(timeout=10.0):
                    logger.error(f"Timeout waiting for first frame from {self.rtsp}")
                    cap.release()
                    cap = None
                    time.sleep(2)
                    continue

            ret, frame = cap.read() #ret: bool, frame: numpy array(ảnh BGR)
            if not ret: #Nếu cap đánh đấu không đọc được qua cờ `ret`
                logger.warning(f"Lost frame from {self.rtsp} - try reconnect...")
                cap.release() #Kill process FFmpeg và giải phóng tài nguyên
                cap = None
                time.sleep(1)
                continue

            if self.latest_frames_ref is not None:
                try:
                    self.latest_frames_ref[self.cam_id] = frame.copy()
                except Exception:
                    pass

            self.inference_engine.put_frame_with_drop(frame, self.cam_id)

            try:
                detections = self.result_queue.get(timeout=0.1)
            except queue.Empty:
                logger.warning(f"Inference timeout for {self.cam_id}, skipping frame")
                time.sleep(0.01)
                continue

            # Cache detections for streaming API
            with self._detections_lock:
                self.latest_detections = detections

            for roi_dict in self.rois:
                node_id = roi_dict["node_id"]
                roi = roi_dict["roi"]
                has_obj, coverage = has_object_in_roi(detections, roi, node_id, use_gpu=True)
                
                #Update state của node_id qua API
                # if self.api_client:
                #     self.api_client.post_detection(self.cam_id, node_id, has_obj, coverage)
                #Update state của node_id trực tiếp
                if self.state_manager:
                    self.state_manager.get_state_nodes(node_id, has_obj)
                #Có thể bỏ nếu không sử dụng snapshot
                if self.snapshot_manager is not None:
                    self.snapshot_manager.update_frame(node_id, frame)

            time.sleep(0.01)

        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass
