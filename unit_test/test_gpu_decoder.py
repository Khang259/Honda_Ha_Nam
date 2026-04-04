# Test script for GPUVideoDecoder
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.gpu_video_decoder import GPUVideoDecoder
import cv2
import time

def test_single_stream():
    print("=== Test Single Stream GPU Decode ===")
    
    rtsp_url = "rtsp://admin:Thado12@@192.168.1.102:554/Streaming/Channels/102"
    
    print(f"Connecting to: {rtsp_url}")
    decoder = GPUVideoDecoder(rtsp_url)
    
    if not decoder.isOpened():
        print("ERROR: Cannot open stream")
        return False
    
    width, height = decoder.get_width_height()
    print(f"Stream resolution: {width}x{height}")
    
    frame_count = 0
    start_time = time.time()
    
    print("Reading frames... (Press 'q' to quit)")
    
    while frame_count < 100:
        ret, frame = decoder.read()
        
        if not ret:
            print(f"ERROR: Failed to read frame {frame_count}")
            break
        
        frame_count += 1
        
        cv2.imshow("GPU Decode Test", frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    elapsed = time.time() - start_time
    fps = frame_count / elapsed
    
    print(f"\nDecoded {frame_count} frames in {elapsed:.2f}s")
    print(f"Average FPS: {fps:.2f}")
    
    decoder.release()
    cv2.destroyAllWindows()
    
    return True

def test_reconnect():
    print("\n=== Test Reconnect Logic ===")
    
    rtsp_url = "rtsp://admin:Thado12@@192.168.1.102:554/Streaming/Channels/102"
    
    decoder = GPUVideoDecoder(rtsp_url)
    
    if not decoder.isOpened():
        print("ERROR: Cannot open stream")
        return False
    
    print("Reading 10 frames...")
    for i in range(10):
        ret, frame = decoder.read()
        if ret:
            print(f"Frame {i+1}: OK")
    
    print("Releasing decoder...")
    decoder.release()
    
    print("Reconnecting...")
    decoder = GPUVideoDecoder(rtsp_url)
    
    if not decoder.isOpened():
        print("ERROR: Cannot reconnect")
        return False
    
    print("Reading 10 more frames after reconnect...")
    for i in range(10):
        ret, frame = decoder.read()
        if ret:
            print(f"Frame {i+1}: OK")
    
    decoder.release()
    print("Reconnect test passed!")
    
    return True

def test_multiple_streams():
    print("\n=== Test Multiple Streams ===")
    
    rtsp_urls = [
        "rtsp://admin:Thado12@@192.168.1.102:554/Streaming/Channels/102",
        "rtsp://admin:Thado12@@192.168.1.105:554/Streaming/Channels/102",
        "rtsp://admin:Thado12@@192.168.1.106:554/Streaming/Channels/102",
        "rtsp://admin:Thado12@@192.168.1.107:554/Streaming/Channels/102",
        "rtsp://admin:Thado12@@192.168.1.108:554/Streaming/Channels/102",
        # "rtsp://admin:Thado12@@192.168.1.109:554/Streaming/Channels/102",
        # "rtsp://admin:Thado12@@192.168.1.110:554/Streaming/Channels/102",
        # "rtsp://admin:Thado12@@192.168.1.111:554/Streaming/Channels/102",
        # "rtsp://admin:Thado12@@192.168.1.112:554/Streaming/Channels/102",
    ]
    
    decoders = []
    
    for url in rtsp_urls:
        decoder = GPUVideoDecoder(url)
        if decoder.isOpened():
            decoders.append(decoder)
            print(f"Opened: {url}")
        else:
            print(f"Failed to open: {url}")
    
    if not decoders:
        print("ERROR: No decoders opened")
        return False
    
    print(f"\nReading 50 frames from {len(decoders)} streams...")
    frame_counts = [0] * len(decoders)
    start_time = time.time()
    
    for _ in range(50):
        for i, decoder in enumerate(decoders):
            ret, frame = decoder.read()
            if ret:
                frame_counts[i] += 1
    
    elapsed = time.time() - start_time
    
    print(f"\nDecoded in {elapsed:.2f}s")
    for i, count in enumerate(frame_counts):
        fps = count / elapsed
        print(f"Stream {i+1}: {count} frames, {fps:.2f} FPS")
    
    for decoder in decoders:
        decoder.release()
    
    print("Multiple streams test passed!")
    return True

if __name__ == "__main__":
    print("GPU Video Decoder Test Suite\n")
    
    try:
        success = True
        
        success &= test_single_stream()
        success &= test_reconnect()
        success &= test_multiple_streams()
        
        if success:
            print("\n✓ All tests passed!")
        else:
            print("\n✗ Some tests failed")
            sys.exit(1)
    
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"\nTest failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
