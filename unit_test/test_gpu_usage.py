"""
Test script để verify GPU usage cho NVDEC decode và ROI calculation.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import torch
from core.gpu_video_decoder import GPUVideoDecoder
from utils.yolo_visualizer import predict_and_visualize
from utils.overlap_utils import calculate_coverage_batch
from ultralytics import YOLO
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("test_gpu_usage")

def print_gpu_memory():
    if torch.cuda.is_available():
        allocated = torch.cuda.memory_allocated() / 1024**2
        reserved = torch.cuda.memory_reserved() / 1024**2
        logger.info(f"GPU Memory: Allocated={allocated:.2f}MB, Reserved={reserved:.2f}MB")
    else:
        logger.warning("CUDA not available")

def test_gpu_decoder():
    logger.info("=" * 60)
    logger.info("TEST 1: GPU Video Decoder (NVDEC)")
    logger.info("=" * 60)
    
    rtsp_url = "rtsp://admin:Thado12@@192.168.1.102:554/Streaming/Channels/102"
    
    logger.info(f"Connecting to {rtsp_url}...")
    cap = GPUVideoDecoder(rtsp_url, width=640, height=480)
    
    if not cap.isOpened():
        logger.error("Failed to open stream")
        return False
    
    logger.info("✅ GPU decoder started successfully")
    
    frame_count = 0
    start_time = time.time()
    
    for i in range(30):
        ret, frame = cap.read()
        if ret and frame is not None:
            frame_count += 1
        time.sleep(0.033)
    
    elapsed = time.time() - start_time
    fps = frame_count / elapsed
    
    logger.info(f"Decoded {frame_count} frames in {elapsed:.2f}s ({fps:.1f} FPS)")
    
    cap.release()
    return True

def test_gpu_roi_calculation():
    logger.info("=" * 60)
    logger.info("TEST 2: GPU ROI Overlap Calculation")
    logger.info("=" * 60)
    
    print_gpu_memory()
    
    detections = torch.tensor([
        [100, 100, 200, 200, 0.9, 0],
        [150, 150, 250, 250, 0.85, 0],
        [300, 300, 400, 400, 0.7, 0],
    ], device='cuda')
    
    roi_box = [120, 120, 100, 100]
    
    logger.info(f"Testing with {len(detections)} detections on GPU")
    
    start = time.time()
    for _ in range(1000):
        coverage = calculate_coverage_batch(detections, roi_box, device='cuda')
    elapsed = time.time() - start
    
    logger.info(f"1000 iterations: {elapsed*1000:.2f}ms ({elapsed*1000/1000:.3f}ms per call)")
    logger.info(f"Coverage results: {coverage}")
    
    print_gpu_memory()
    return True

def test_full_pipeline():
    logger.info("=" * 60)
    logger.info("TEST 3: Full Pipeline (Decode → YOLO → ROI)")
    logger.info("=" * 60)
    
    print_gpu_memory()
    
    rtsp_url = "rtsp://admin:Thado12@@192.168.1.102:554/Streaming/Channels/102"
    
    logger.info("Loading YOLO model...")
    model = YOLO("models/ModelHNAE_12022601.pt", verbose=False)
    
    logger.info("Starting GPU decoder...")
    cap = GPUVideoDecoder(rtsp_url, width=640, height=480)
    
    if not cap.isOpened():
        logger.error("Failed to open stream")
        return False
    
    roi_box = [163, 156, 79, 66]
    
    print_gpu_memory()
    
    frame_count = 0
    detect_count = 0
    total_latency = 0
    
    logger.info("Processing frames...")
    
    for i in range(50):
        start = time.time()
        
        ret, frame = cap.read()
        if not ret or frame is None:
            continue
        
        detections, annotated = predict_and_visualize(model, frame, return_tensor=True)
        
        if len(detections) > 0:
            vehicle_mask = (detections[:, 5] == 0) & (detections[:, 4] > 0.3)
            vehicle_detections = detections[vehicle_mask]
            
            if len(vehicle_detections) > 0:
                coverage = calculate_coverage_batch(vehicle_detections, roi_box, device='cuda')
                max_coverage = torch.max(coverage)
                
                if max_coverage >= 0.5:
                    detect_count += 1
        
        frame_count += 1
        latency = (time.time() - start) * 1000
        total_latency += latency
        
        if i % 10 == 0:
            logger.info(f"Frame {frame_count}: latency={latency:.1f}ms")
    
    avg_latency = total_latency / frame_count
    
    logger.info(f"Processed {frame_count} frames")
    logger.info(f"Detections in ROI: {detect_count} frames")
    logger.info(f"Average latency: {avg_latency:.1f}ms ({1000/avg_latency:.1f} FPS)")
    
    print_gpu_memory()
    
    cap.release()
    return True

def main():
    logger.info("GPU Usage Verification Test")
    logger.info("=" * 60)
    
    if not torch.cuda.is_available():
        logger.error("CUDA not available! Cannot test GPU features.")
        return
    
    logger.info(f"CUDA Device: {torch.cuda.get_device_name(0)}")
    print_gpu_memory()
    
    logger.info("\n")
    
    try:
        if test_gpu_decoder():
            logger.info("✅ GPU Decoder test PASSED\n")
        else:
            logger.error("❌ GPU Decoder test FAILED\n")
        
        if test_gpu_roi_calculation():
            logger.info("✅ GPU ROI calculation test PASSED\n")
        else:
            logger.error("❌ GPU ROI calculation test FAILED\n")
        
        if test_full_pipeline():
            logger.info("✅ Full pipeline test PASSED\n")
        else:
            logger.error("❌ Full pipeline test FAILED\n")
        
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    logger.info("=" * 60)
    logger.info("Test completed")

if __name__ == "__main__":
    main()
