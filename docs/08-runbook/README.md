# Runbook - Vận hành hệ thống

> **Đọc phần này nếu**: Bạn cần start/stop/restart hệ thống, hoặc vận hành daily operations.

## Nội dung

### 🚀 [Startup Procedure](./startup-procedure.md)
Hướng dẫn start toàn bộ system từ đầu.

**Steps**:
1. Check prerequisites (MongoDB, GPU)
2. Start service
3. Verify health
4. Enable cameras

---

### 🔄 [Restart Procedures](./restart-procedures.md)
Restart từng service/component độc lập.

**Scenarios**:
- Restart toàn bộ service
- Restart chỉ inference engine
- Restart worker (graceful)
- Force restart (emergency)

---

### 📋 [DISTRIBUTED_FAILOVER_TESTING](./DISTRIBUTED_FAILOVER_TESTING.md)
Hướng dẫn test distributed failover và rebalancing.

**Tests**:
- Worker join/leave
- Network partition
- MongoDB connection loss
- Camera failover

---

### 🎛️ [CAMERA_CONTROL_TEST_GUIDE](./CAMERA_CONTROL_TEST_GUIDE.md)
Hướng dẫn test camera control features.

**Tests**:
- Toggle single camera
- Toggle all cameras
- Zone-based control
- Concurrent requests

---

### 📊 [Health Checks](./health-checks.md)
Kiểm tra health của từng component.

**Checks**:
- Service health (GET /health)
- Runtime status (GET /runtime/status)
- Camera alive count
- Inference throughput
- Worker heartbeat

---

### 📝 [Log Analysis](./log-analysis.md)
Đọc và phân tích logs.

**Common Patterns**:
- Camera reconnect
- Inference timeout
- Pair sent/failed
- Worker rebalance

---

### 🔧 [Configuration Changes](./config-changes.md)
Thay đổi config mà không restart.

**Hot Reload**:
- MongoDB configs (camera, ROI, pairs)
- Worker assignment
- Model reload (future)

---

## Daily Operations

### Morning Checklist
- [ ] Check service health (GET /health)
- [ ] Verify all cameras alive
- [ ] Check pair sent rate (last 1h)
- [ ] Review error logs

### During Shift
- [ ] Monitor GPU utilization
- [ ] Watch for camera reconnects
- [ ] Check inference throughput
- [ ] Respond to alerts

### End of Shift
- [ ] Review daily metrics
- [ ] Document incidents
- [ ] Plan maintenance

---

## Emergency Procedures

### Service Down
```bash
# 1. Check process
ps aux | grep python

# 2. Check logs
tail -100 logs/ai_main/log_$(date +%Y%m%d).log

# 3. Restart
python -m api.main_ai
```

### High CPU/Memory
```bash
# 1. Check resource usage
top -p <pid>

# 2. Thread dump
kill -SIGUSR1 <pid>  # (nếu có signal handler)

# 3. Consider restart
```

### Camera Offline
```bash
# 1. Check network
ping <camera_ip>

# 2. Check RTSP
ffmpeg -i rtsp://<camera_ip>/stream -frames:v 1 test.jpg

# 3. Toggle camera (để force reconnect)
curl -X POST http://localhost:8000/engine-control/toggle \
  -H 'Content-Type: application/json' \
  -d '{"cameraId": 101}'
```

---

## Maintenance Windows

### Weekly Maintenance
- [ ] Review and cleanup logs
- [ ] Check disk space
- [ ] MongoDB backup
- [ ] Update validate_pairs nếu cần

### Monthly Maintenance
- [ ] Review performance trends
- [ ] Update dependencies (security patches)
- [ ] Optimize MongoDB indexes
- [ ] Load test với peak traffic

---

[⬅️ Về trang chủ](../README.md) | [➡️ Tiếp: Troubleshooting](../09-troubleshooting/)
