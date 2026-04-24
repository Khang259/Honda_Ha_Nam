# Troubleshooting - Xử lý sự cố

> **Đọc phần này nếu**: Hệ thống có vấn đề và bạn cần fix nhanh.

## 🔴 Critical Issues (P0)

### [Service Won't Start](./service-wont-start.md)
**Triệu chứng**: `python -m api.main_ai` exit ngay hoặc crash

**Quick Fix**:
1. Check MongoDB connection
2. Check GPU availability
3. Check .env file

---

### [All Cameras Offline](./all-cameras-offline.md)
**Triệu chứng**: Không có camera nào stream

**Quick Fix**:
1. Check network
2. Verify MongoDB camera configs
3. Check worker assignment

---

### [GPU Out of Memory](./gpu-oom.md)
**Triệu chứng**: CUDA out of memory error

**Quick Fix**:
1. Giảm `INFERENCE_MAX_BATCH_SIZE`
2. Kill other GPU processes
3. Restart service

---

## ⚠️ High Priority (P1)

### [High Frame Drop Rate](./frame-drop.md)
**Triệu chứng**: Frame drop rate > 5%

**Debug Steps**:
1. Check inference queue depth
2. Monitor GPU utilization
3. Tune batch timeout

---

### [Inference Timeout](./inference-timeout.md)
**Triệu chứng**: Log nhiều "Inference timeout"

**Debug Steps**:
1. Check batch size vs GPU capacity
2. Monitor CUDA stream status
3. Check model load

---

### [Worker Not Rebalancing](./worker-rebalance.md)
**Triệu chứng**: Worker die nhưng cameras không reassign

**Debug Steps**:
1. Check heartbeat timeout config
2. Verify MongoDB worker_registry
3. Check fencing tokens

---

## 📋 Medium Priority (P2)

### [Camera Keeps Reconnecting](./camera-reconnect.md)
**Triệu chứng**: Camera reconnect > 5 times/hour

**Possible Causes**:
- Network instability
- RTSP URL timeout
- Camera firmware issue

---

### [Pair Not Sent to ICS](./pair-not-sent.md)
**Triệu chứng**: Ready pair nhưng không gửi webhook

**Debug Steps**:
1. Check validate_pairs trong DB
2. Verify ICS_URL reachable
3. Check pair_manager logs

---

### [Streaming Lag](./streaming-lag.md)
**Triệu chứng**: MJPEG stream chậm hoặc freeze

**Possible Causes**:
- Too many concurrent clients
- Encoding bottleneck
- MongoDB ROI query slow

---

## 🔧 Debug Tools

### Check Service Status
```bash
curl http://localhost:8000/health
curl http://localhost:8000/runtime/status
```

### Check Logs
```bash
# Latest errors
tail -100 logs/ai_main/log_$(date +%Y%m%d).log | grep ERROR

# Follow live logs
tail -f logs/inference_engine/log_$(date +%Y%m%d).log
```

### Check GPU
```bash
# GPU usage
nvidia-smi

# CUDA processes
nvidia-smi pmon

# GPU memory breakdown
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
```

### Check MongoDB
```bash
# Connect to MongoDB
mongosh <MongoDB_URL>

# Check collections
use <MongoDB_DB>
db.node_id.countDocuments()
db.worker_registry.find()
```

### Check Network
```bash
# Camera reachable
ping <camera_ip>

# RTSP test
ffprobe rtsp://<camera_ip>/stream

# Port listening
netstat -an | grep 8000
```

---

## Common Error Messages

### "Camera manager not initialized"
**Cause**: API called trước khi runtime start

**Fix**: Đợi runtime start xong (check `/runtime/status`)

---

### "Inference timeout"
**Cause**: Inference quá chậm, camera không nhận được result

**Fix**: 
- Giảm batch_size
- Tăng timeout
- Check GPU load

---

### "MongoDB connection refused"
**Cause**: MongoDB không chạy hoặc network issue

**Fix**:
- Start MongoDB: `sudo systemctl start mongodb`
- Check firewall
- Verify MongoDB_URL trong .env

---

### "CUDA out of memory"
**Cause**: Model + batch quá lớn cho GPU

**Fix**:
- Giảm `INFERENCE_MAX_BATCH_SIZE`
- Kill other GPU processes
- Upgrade GPU (nếu cần)

---

### "Camera not found"
**Cause**: cameraId không tồn tại trong configs

**Fix**:
- GET `/engine-control/cameras` để xem list
- Check MongoDB node_id collection
- Verify worker assignment

---

## Escalation Path

### Level 1 (Self-Service)
- Check docs/troubleshooting
- Review logs
- Try common fixes

### Level 2 (Team Lead)
- Complex debugging
- Config changes
- Performance tuning

### Level 3 (Dev Team)
- Code bugs
- Architecture issues
- New features needed

---

[⬅️ Về trang chủ](../README.md)
