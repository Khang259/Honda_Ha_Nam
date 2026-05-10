import subprocess
import threading
import queue
import numpy as np
from config import GPU_DECODE_BUFFER_SIZE, FFMPEG_RECONNECT_DELAY, FFMPEG_MAX_RETRIES
from shared.setup_log import setup_logger

logger = setup_logger("gpu_video_decoder", "logs/gpu_decoder/log")

class GPUVideoDecoder:
    """
    Giải mã video RTSP bằng FFmpeg NVDEC (GPU), đọc frame raw BGR ra queue cho consumer.
    """

    def __init__(self, rtsp_url, width=640, height=480):
        """Khởi tạo decoder: lưu URL/kích thước, tạo queue 3 frame, và gọi _start_decode()."""
        self.rtsp_url = rtsp_url
        self.width = width
        self.height = height
        self.frame_size = width * height * 3
        
        self.queue = queue.Queue(maxsize=3)
        self.process = None
        self.thread = None
        self.running = False
        self._opened = False
        self._ready = threading.Event()
        
        self._start_decode()

    
    def _decode_loop(self):
        """Vòng lặp đọc stdout FFmpeg theo frame_size, chuyển raw -> numpy BGR, bỏ frame cũ nếu queue đầy rồi put vào queue; set _ready khi có frame đầu."""
        first_frame = True
        while self.running:
            try:
                raw = self.process.stdout.read(self.frame_size)
                if len(raw) != self.frame_size:
                    continue

                frame = np.frombuffer(raw, np.uint8).reshape((self.height, self.width, 3))

                if first_frame: 
                    self._ready.set() #Kích hoạt event threading for what?
                    first_frame = False

                if self.queue.full(): #Nếu đầy thì sử dụng get_nowait() để xóa frame cũ
                    try:
                        self.queue.get_nowait()
                    except queue.Empty: #Nếu queue rỗng thì pass
                        pass

                self.queue.put(frame) #và put frame mới
            except Exception as e:
                logger.error(f"Decode error: {e}")
                break

    def _start_decode(self):
        """Chạy FFmpeg với hwaccel cuda (NVDEC), pipe stdout raw BGR; khởi động thread _decode_loop."""
        if self.running:
            return

        cmd = [
            "ffmpeg",
            "-hwaccel", "cuda",
            # "-hwaccel_output_format", "cuda",
            "-rtsp_transport", "tcp",
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-i", self.rtsp_url,
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{self.width}x{self.height}",
            "-"
        ]

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=GPU_DECODE_BUFFER_SIZE
            )
            
            self.running = True
            self._opened = True
            self.thread = threading.Thread(target=self._decode_loop, daemon=True)
            self.thread.start()
            
            #logger.info(f"Started GPU decode for {self.rtsp_url} with hwaccel nvdec")
        except Exception as e:
            logger.error(f"Failed to start FFmpeg: {e}")
            self._opened = False

    def isOpened(self):
        """Trả về True nếu decoder đã mở và process FFmpeg vẫn đang chạy (poll() is None)."""
        return self._opened and self.process is not None and self.process.poll() is None

    def read(self):
        """Lấy một frame từ queue (non-blocking). Trả về (True, frame) nếu có, (False, None) nếu queue rỗng hoặc decoder đóng."""
        if not self.isOpened():
            return False, None
            
        if not self.queue.empty():
            frame = self.queue.get()
            return True, frame
        return False, None
    
    def wait_ready(self, timeout=10.0):
        """
        Chờ đến khi có frame đầu tiên decode xong (block). Dùng trước khi đọc frame để tránh read() rỗng.
        Args:
            timeout: Thời gian chờ tối đa (giây), mặc định 10.0.
        Returns:
            True nếu sẵn sàng trong timeout, False nếu hết giờ.
        """
        is_ready = self._ready.wait(timeout)
        if is_ready:
            logger.info(f"Decoder ready for {self.rtsp_url}")
        else:
            logger.warning(f"Decoder timeout waiting for first frame from {self.rtsp_url}")
        return is_ready

    def release(self):
        """Dừng decode loop, kill process FFmpeg, chờ tối đa 2s; giải phóng tài nguyên."""
        self.running = False
        self._opened = False
        
        if self.process:
            try:
                self.process.kill()
                self.process.wait(timeout=2)
            except:
                pass
            self.process = None