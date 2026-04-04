#!/usr/bin/env python3
"""
Test CUDA Stream Overlap
Kiểm tra xem 3 CUDA streams có chạy song song (overlap) hay không.
"""

import torch
import time
import numpy as np
from collections import deque
import sys

print("=" * 70)
print("CUDA STREAM OVERLAP TEST")
print("=" * 70)

# Check CUDA availability
if not torch.cuda.is_available():
    print("❌ CUDA not available!")
    sys.exit(1)

print(f"✓ CUDA available: {torch.cuda.get_device_name(0)}")
print(f"✓ CUDA version: {torch.version.cuda}")
print()

def test_simple_overlap():
    """Test 1: Simple matrix multiplication overlap test."""
    print("Test 1: Simple Matrix Multiplication Overlap")
    print("-" * 70)
    
    num_streams = 3
    streams = [torch.cuda.Stream() for _ in range(num_streams)]
    events_start = []
    events_end = []
    
    print(f"Created {num_streams} CUDA streams")
    
    # Launch work on all streams
    for i, stream in enumerate(streams):
        with torch.cuda.stream(stream):
            # Create start event
            start_event = torch.cuda.Event(enable_timing=True)
            start_event.record(stream)
            events_start.append(start_event)
            
            # Heavy computation
            x = torch.randn(2000, 2000, device='cuda')
            for _ in range(200):
                x = x @ x
            
            # Create end event
            end_event = torch.cuda.Event(enable_timing=True)
            end_event.record(stream)
            events_end.append(end_event)
    
    # Check immediately after launch
    time.sleep(0.001)  # Small delay to let kernels launch
    
    active_count = sum(1 for e in events_end if not e.query())
    print(f"Active streams right after launch: {active_count}/{num_streams}")
    
    if active_count >= 2:
        print("✅ RESULT: STREAMS ARE OVERLAPPING!")
    elif active_count == 1:
        print("⚠️  RESULT: Only 1 stream active (possible overlap but weak)")
    else:
        print("❌ RESULT: NO OVERLAP DETECTED (Sequential execution)")
    
    # Wait for all to complete
    torch.cuda.synchronize()
    
    # Calculate elapsed times (skip if error)
    try:
        print("\nStream execution times:")
        for i in range(num_streams):
            # Synchronize events before measuring
            events_end[i].synchronize()
            elapsed = events_start[i].elapsed_time(events_end[i])
            print(f"  Stream {i}: {elapsed:.2f} ms")
    except RuntimeError as e:
        print(f"  (Could not measure elapsed time: {e})")
    
    print()
    return active_count >= 2


def test_yolo_like_overlap():
    """Test 2: YOLO-like inference pattern overlap test."""
    print("Test 2: YOLO-like Inference Pattern")
    print("-" * 70)
    
    try:
        from ultralytics import YOLO
    except ImportError:
        print("⚠️  Ultralytics not available, skipping YOLO test")
        return None
    
    num_streams = 3
    streams = [torch.cuda.Stream() for _ in range(num_streams)]
    pending_batches = deque(maxlen=6)
    
    # Create dummy frames (simulating camera input)
    batch_size = 12
    dummy_frames = [np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8) 
                    for _ in range(batch_size * num_streams)]
    
    print(f"Launching {num_streams} inference batches...")
    
    # Launch inference on all streams
    stream_idx = 0
    for batch_idx in range(num_streams):
        stream = streams[stream_idx]
        batch_start = batch_idx * batch_size
        batch_end = batch_start + batch_size
        batch_frames = dummy_frames[batch_start:batch_end]
        
        with torch.cuda.stream(stream):
            # Simulate preprocessing
            tensors = torch.randn(batch_size, 3, 640, 640, device='cuda')
            
            # Simulate inference with consistent dimensions
            # First conv: 3 → 32 channels
            tensors = torch.nn.functional.conv2d(
                tensors, 
                torch.randn(32, 3, 3, 3, device='cuda'),
                padding=1
            )
            
            # Subsequent convs: 32 → 32 channels
            for _ in range(99):
                tensors = torch.nn.functional.conv2d(
                    tensors, 
                    torch.randn(32, 32, 3, 3, device='cuda'),  # ← 32 input channels
                    padding=1
                )
            
            event = torch.cuda.Event()
            event.record(stream)
        
        pending_batches.append({
            'stream_idx': stream_idx,
            'event': event,
            'timestamp': time.time()
        })
        
        stream_idx = (stream_idx + 1) % num_streams
    
    # Check overlap immediately
    time.sleep(0.01)
    active_count = sum(1 for b in pending_batches if not b['event'].query())
    
    print(f"Active streams after launch: {active_count}/{num_streams}")
    
    if active_count >= 2:
        print("✅ RESULT: YOLO-like pattern shows OVERLAP!")
        result = True
    else:
        print("❌ RESULT: YOLO-like pattern shows NO OVERLAP!")
        result = False
    
    # Wait for completion
    torch.cuda.synchronize()
    print()
    
    return result


def test_context_manager_blocking():
    """Test 3: Check if 'with torch.cuda.stream()' blocks."""
    print("Test 3: Context Manager Blocking Test")
    print("-" * 70)
    
    stream = torch.cuda.Stream()
    
    # Test 1: With context manager
    print("Testing 'with torch.cuda.stream()' pattern...")
    start = time.perf_counter()
    
    with torch.cuda.stream(stream):
        x = torch.randn(2000, 2000, device='cuda')
        for _ in range(100):
            x = x @ x
        event = torch.cuda.Event()
        event.record(stream)
    
    elapsed_with_context = (time.perf_counter() - start) * 1000
    
    # Check if event is already completed
    is_completed = event.query()
    
    print(f"  Time in context: {elapsed_with_context:.2f} ms")
    print(f"  Event completed on exit: {is_completed}")
    
    if is_completed:
        print("  ⚠️  Context manager BLOCKS (waits for completion)")
    else:
        print("  ✅ Context manager is NON-BLOCKING")
    
    torch.cuda.synchronize()
    print()
    
    return not is_completed


def test_inference_engine_pattern():
    """Test 4: Replicate actual InferenceEngine pattern."""
    print("Test 4: InferenceEngine Pattern Replication")
    print("-" * 70)
    
    num_streams = 3
    streams = [torch.cuda.Stream() for _ in range(num_streams)]
    pending_batches = deque(maxlen=6)
    
    print("Simulating InferenceEngine run() loop pattern...")
    
    stream_idx = 0
    total_active = []
    
    # Simulate 10 iterations
    for iteration in range(10):
        # Launch inference (like in run() loop)
        stream = streams[stream_idx]
        
        with torch.cuda.stream(stream):
            x = torch.randn(1000, 1000, device='cuda')
            for _ in range(50):
                x = x @ x
            event = torch.cuda.Event()
            event.record(stream)
        
        pending_batches.append({
            'event': event,
            'stream': stream_idx
        })
        
        stream_idx = (stream_idx + 1) % num_streams
        
        # Check completed (like in run() loop)
        completed = []
        for i, batch_info in enumerate(pending_batches):
            if batch_info['event'].query():
                completed.append(i)
        
        for i in reversed(completed):
            pending_batches.remove(list(pending_batches)[i])
        
        # Check active streams
        active = len(pending_batches)
        total_active.append(active)
        
        if iteration < 5:
            print(f"  Iteration {iteration}: {active} pending batches")
    
    avg_active = sum(total_active) / len(total_active)
    max_active = max(total_active)
    
    print(f"\nResults:")
    print(f"  Average pending batches: {avg_active:.1f}")
    print(f"  Maximum pending batches: {max_active}")
    
    if max_active >= 2:
        print("  ✅ Pipeline shows OVERLAP potential")
        result = True
    else:
        print("  ❌ Pipeline is SEQUENTIAL (no overlap)")
        result = False
    
    torch.cuda.synchronize()
    print()
    
    return result


def monitor_gpu_utilization():
    """Test 5: GPU utilization during overlap test."""
    print("Test 5: GPU Utilization Test")
    print("-" * 70)
    
    try:
        import subprocess
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'],
            capture_output=True,
            text=True,
            timeout=2
        )
        baseline_util = int(result.stdout.strip())
        print(f"Baseline GPU utilization: {baseline_util}%")
    except:
        print("⚠️  Could not read GPU utilization (nvidia-smi not available)")
        return None
    
    # Launch heavy workload on 3 streams
    streams = [torch.cuda.Stream() for _ in range(3)]
    events = []
    
    print("Launching heavy workload on 3 streams...")
    for stream in streams:
        with torch.cuda.stream(stream):
            x = torch.randn(3000, 3000, device='cuda')
            for _ in range(500):
                x = x @ x
            event = torch.cuda.Event()
            event.record(stream)
            events.append(event)
    
    # Quick check utilization
    time.sleep(0.1)
    
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'],
            capture_output=True,
            text=True,
            timeout=2
        )
        peak_util = int(result.stdout.strip())
        print(f"Peak GPU utilization: {peak_util}%")
        
        if peak_util > 80:
            print("  ✅ High GPU utilization suggests OVERLAP")
        elif peak_util > 50:
            print("  ⚠️  Medium GPU utilization - partial overlap")
        else:
            print("  ❌ Low GPU utilization - likely NO overlap")
    except:
        print("  ⚠️  Could not measure peak utilization")
    
    torch.cuda.synchronize()
    print()


def main():
    """Run all tests."""
    results = []
    
    # Run tests
    results.append(("Simple Overlap", test_simple_overlap()))
    results.append(("YOLO-like Pattern", test_yolo_like_overlap()))
    results.append(("Non-blocking Context", test_context_manager_blocking()))
    results.append(("InferenceEngine Pattern", test_inference_engine_pattern()))
    monitor_gpu_utilization()
    
    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    for test_name, result in results:
        if result is None:
            status = "SKIPPED"
            emoji = "⊝"
        elif result:
            status = "PASS (Overlap detected)"
            emoji = "✅"
        else:
            status = "FAIL (No overlap)"
            emoji = "❌"
        
        print(f"{emoji} {test_name:30s}: {status}")
    
    print()
    
    # Overall verdict
    valid_results = [r for _, r in results if r is not None]
    if not valid_results:
        print("⚠️  No valid test results")
    elif all(valid_results):
        print("🎉 OVERALL: CUDA streams ARE overlapping correctly!")
    elif any(valid_results):
        print("⚠️  OVERALL: PARTIAL overlap detected (needs investigation)")
    else:
        print("⛔ OVERALL: NO overlap detected (sequential execution)")
        print("\nPossible causes:")
        print("  1. 'with torch.cuda.stream()' context manager blocks on exit")
        print("  2. YOLO model forces synchronization internally")
        print("  3. Small workload completes before next stream launches")
        print("\nRecommendations:")
        print("  - Use ThreadPoolExecutor for true parallel execution")
        print("  - Profile with 'nsys profile python main_ai.py'")
        print("  - Check GPU utilization with 'nvidia-smi dmon'")
    
    print("=" * 70)


if __name__ == "__main__":
    main()
