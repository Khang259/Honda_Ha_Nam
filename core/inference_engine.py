# File: inference_engine.py
import threading
import queue
import time
from collections import deque
import numpy as np
import torch
from ultralytics import YOLO
from utils.setup_log import setup_logger
import pathlib
import platform
if platform.system() == 'Windows':
    pathlib.PosixPath = pathlib.WindowsPath


logger = setup_logger("inference_engine", "logs/inference_engine/log")

class InferenceEngine(threading.Thread):
    """
    Central inference engine với single model instance, batch processing và CUDA stream async.
    """
    
    def __init__(
        self,
        model_path,
        max_queue_size,
        max_batch_size,
        batch_timeout,
        num_streams,
        initial_paused: bool = False,
    ):
        """
        Args:
            model_path: Path đến YOLO model
            max_queue_size: Kích thước tối đa của shared queue
            max_batch_size: Số lượng frames tối đa trong 1 batch
            batch_timeout: Thời gian chờ tối đa để collect batch (seconds)
            num_streams: Số lượng CUDA streams cho async pipeline
            pending_batches: batches frames chờ CUDA streams
        """
        super().__init__(daemon=True, name="InferenceEngine")
        
        self.model_path = model_path
        self.max_queue_size = max_queue_size
        self.max_batch_size = max_batch_size
        self.batch_timeout = batch_timeout
        self.num_streams = num_streams
        self.shared_queue = queue.Queue(maxsize=max_queue_size)
        self.result_queues = {}
        self.streams = [] 
        self.pending_batches = deque(maxlen=num_streams * 2)
        self.running = False
        self.model = None
        # Pause inference execution (thread still alive, model already loaded).
        self._paused = threading.Event()
        if initial_paused:
            self._paused.set()

    def pause(self) -> None:
        """Pause inference pipeline execution."""
        self._paused.set()
        logger.info("InferenceEngine paused")

    def resume(self) -> None:
        """Resume inference pipeline execution."""
        self._paused.clear()
        logger.info("InferenceEngine resumed")
    
    def register_camera(self, cam_id, result_queue):
        """
        Đăng ký result queue cho camera.
        
        Args:
            cam_id: ID của camera
            result_queue: Queue để trả kết quả về camera thread
        """
        self.result_queues[cam_id] = result_queue
    
    def put_frame_with_drop(self, frame, cam_id):
        """
        Put frame vào shared queue, drop oldest nếu queue full.
        
        Args:
            frame: numpy array (H, W, 3)
            cam_id: ID của camera
        """
        try:
            self.shared_queue.put_nowait((frame, cam_id))
        except queue.Full:
            # Drop oldest frame
            try:
                dropped_frame, dropped_cam_id = self.shared_queue.get_nowait()
                #logger.warning(f"Queue full, dropped frame from {dropped_cam_id}")
            except queue.Empty:
                pass
    
    def _collect_batch(self):
        """
        Collect batch frames từ shared queue với timeout.
        
        Returns:
            tuple: (batch_frames, cam_ids) - list of frames và corresponding cam_ids
        """
        batch = []
        cam_ids = []
        start_time = time.time()
        
        while len(batch) < self.max_batch_size:
            timeout = self.batch_timeout - (time.time() - start_time)
            if timeout <= 0:
                break
            
            try:
                frame, cam_id = self.shared_queue.get(timeout=timeout)
                batch.append(frame)
                cam_ids.append(cam_id)
            except queue.Empty:
                break
        
        return batch, cam_ids
    
    def _load_model(self):
        """Load YOLO model instance và tạo CUDA streams."""
        try:
            self.model = YOLO(self.model_path, verbose=False)
            self.streams = [torch.cuda.Stream() for _ in range(self.num_streams)] #create CUDA streams
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise
    
    def _async_inference(self, frames_batch, stream):
        """
        Inference async trên CUDA stream cụ thể.
        
        Args:
            frames_batch: List[np.ndarray] - batch frames
            stream: torch.cuda.Stream - CUDA stream để chạy inference
            
        Returns:
            tuple: (results, event) - results là list detections, event để check completion
        """
        with torch.cuda.stream(stream):
            results = self.model(frames_batch, 
                               conf=0.3, 
                               max_det=15,
                               device='cuda',
                               verbose=False,
                               stream=True)
            
            output = []
            for result in results:
                detections = result.boxes.data #TODO: check this code is applicable for GPU inference in batch processing
                output.append(detections)
            
            event = stream.record_event() #Ghi CUDA Event vào stream và để đồng bộ giữa các stream
            
        return output, event
    
    def _distribute_results(self, results, cam_ids):
        """
        Phân phối results về các camera threads.
        
        Args:
            results: List[torch.Tensor] - detection results
            cam_ids: List[str] - corresponding camera IDs
        """
        for detection, cam_id in zip(results, cam_ids):
            if cam_id not in self.result_queues:
                logger.warning(f"Camera {cam_id} not registered")
                continue
                
            try:
                self.result_queues[cam_id].put_nowait(detection)
            except queue.Full:
                try:
                    self.result_queues[cam_id].get_nowait() #? Nếu queue full get_nowait() lấy gì
                    self.result_queues[cam_id].put_nowait(detection)
                except (queue.Empty, queue.Full):
                    logger.warning(f"Failed to deliver result to {cam_id}")
    
    def run(self):
        """Main loop với async CUDA stream pipeline."""
        self.running = True
        self._load_model()
        
        #logger.info("InferenceEngine async pipeline started")
        
        stream_idx = 0
        
        while self.running:
            try:
                # When paused, do not collect frames / run CUDA inference.
                if self._paused.is_set():
                    time.sleep(0.05)
                    continue

                batch_frames, cam_ids = self._collect_batch()
                """
                Nếu số lượng batch có frames > 0 thì 
                gán batch_frames vào resultm stream vào event để chạy async_inference 
                """
                if len(batch_frames) > 0: 
                    stream = self.streams[stream_idx]
                    
                    results, event = self._async_inference(batch_frames, stream) # Gán event vào stream thông qua hàm _async_inference
                    #Thêm kết quả vào list(pending_batches)
                    self.pending_batches.append({
                        'results': results,
                        'cam_ids': cam_ids,
                        'event': event,
                        'timestamp': time.time()
                    })
                    
                    stream_idx = (stream_idx + 1) % self.num_streams
                
                completed_indices = []
                for i, batch_info in enumerate(self.pending_batches):
                    if batch_info['event'].query(): #check if event of the object `batch_info['event']` is ready
                        self._distribute_results(batch_info['results'], batch_info['cam_ids'])
                        completed_indices.append(i)
                
                for i in reversed(completed_indices):
                    del self.pending_batches[i]
                
                if len(batch_frames) == 0 and len(self.pending_batches) == 0:
                    time.sleep(0.1) #Wait for frames to be collected
                
            except Exception as e:
                logger.error(f"Error in inference loop: {e}", exc_info=True)
                time.sleep(0.1)
        
        logger.info("InferenceEngine stopped")
    
    def stop(self):
        """Stop inference engine."""
        self.running = False
        logger.info("Stopping InferenceEngine...")