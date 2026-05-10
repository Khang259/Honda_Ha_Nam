# test_model_rtsp.py
# Script test để kiểm tra model YOLO với RTSP stream sử dụng GPU (nếu có sẵn).
# Yêu cầu: 
# - Đã cài đặt ultralytics, opencv-python (cv2), torch (với CUDA nếu sử dụng GPU).
# - File model "model_vl_0205.pt" phải tồn tại trong thư mục hiện tại hoặc chỉ định đường dẫn đầy đủ.
# - RTSP stream phải đang chạy tại rtsp://127.0.0.1:8554/start.
# - Môi trường Windows: Đảm bảo driver GPU (NVIDIA CUDA) đã cài đặt nếu muốn sử dụng GPU.
# - Script này sẽ đọc frame từ RTSP, crop một ROI mẫu (hardcode từ config), detect object sử dụng model,
#   vẽ bounding boxes lên ROI nếu detect (class 0, conf > threshold), hiển thị trực quan bằng cv2.imshow,
#   và log kết quả. 
# - Lưu ý: Trên Windows server headless (không có GUI), cv2.imshow có thể gây error. Chỉ dùng cho môi trường có display.
# - Để thoát: Nhấn phím ESC.

import cv2
import torch
from ultralytics import YOLO
import time
import logging
import pathlib
import platform
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from inference_core.gpu_video_decoder import GPUVideoDecoder

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("test_model")

# Cấu hình
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
THRESHOLD_DETECT = 0.6  
TARGET_CLASS = 0  # Assume class 0 là object cần detect

if platform.system() == 'Windows':
    pathlib.PosixPath = pathlib.WindowsPath

def main():
    # Load model
    model_path = "ModelHNAE_090326_01.pt"  # Thay đổi nếu model ở đường dẫn khác
    try:
        model = YOLO(model_path, verbose=False, task="detect")
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        return

    # Kiểm tra và sử dụng GPU nếu có sẵn
    # if torch.cuda.is_available():
    #     model.to('cuda')
    #     logger.info("Using GPU (CUDA) for model inference.")
    # else:
    #     logger.warning("GPU not available, using CPU.")

    # Kết nối RTSP với GPU decoder
    rtsp_url = "rtsp://admin:Thado12@@192.168.1.171:554/Streaming/Channels/102"
    cap = GPUVideoDecoder(rtsp_url, width=FRAME_WIDTH, height=FRAME_HEIGHT)
    if not cap.isOpened():
        logger.error(f"Failed to open RTSP stream: {rtsp_url}")
        return

    logger.info(f"Connected to RTSP: {rtsp_url} with GPU decode. Starting test loop...")

    try:
        frame_count = 0
        start_time = time.time()
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                logger.warning("Failed to read frame, retrying...")
                time.sleep(1)
                continue

            frame_count += 1

            # Detect trên full frame
            results = model(frame)
            detections = results[0].boxes.data.cpu().numpy()

            # Lọc detections cho class 0 và conf > threshold
            filtered_dets = detections[(detections[:, 5] == TARGET_CLASS) & (detections[:, 4] > THRESHOLD_DETECT)]

            has_object = len(filtered_dets) > 0

            # Vẽ bounding boxes lên full frame
            display_frame = frame.copy()
            for det in filtered_dets:
                bx1, by1, bx2, by2, conf, cls = det
                cv2.rectangle(display_frame, (int(bx1), int(by1)), (int(bx2), int(by2)), (0, 255, 0), 2)
                cv2.putText(display_frame, f"Class: {int(cls)} Conf: {conf:.2f}", 
                            (int(bx1), int(by1) - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            # Thêm info text lên frame
            info_text = f"Frame: {frame_count} | Objects: {len(filtered_dets)}"
            cv2.putText(display_frame, info_text, (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

            # Hiển thị full frame với detections
            cv2.imshow("Full Frame Detection", display_frame)

            logger.info(f"Frame {frame_count}: Objects detected: {len(filtered_dets)}")

            # Kiểm tra phím ESC để thoát
            if cv2.waitKey(1) & 0xFF == 27:  # 27 là mã ASCII của ESC
                logger.info("ESC pressed. Exiting...")
                break

            # Giới hạn FPS ~10 để tránh overload
            time.sleep(0.1)

            # Test 60 giây rồi dừng (có thể chỉnh hoặc bỏ nếu muốn chạy vô hạn)
            if time.time() - start_time > 999:
                logger.info("Test completed after 60 seconds.")
                break

    except KeyboardInterrupt:
        logger.info("Test interrupted by user.")
    except Exception as e:
        logger.error(f"Error during test: {e}")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        logger.info("RTSP connection closed and windows destroyed.")

if __name__ == "__main__":
    main()