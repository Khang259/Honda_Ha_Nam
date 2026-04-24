# Technical Documentation

> **Đọc phần này nếu**: Bạn cần maintain hệ thống, optimize performance, hoặc debug issues.

## Nội dung

### 🔧 [Performance Tuning](./performance-tuning.md)
Hướng dẫn tune parameters để tối ưu throughput/latency.

**Topics**:
- Batch size tuning
- CUDA streams optimization
- Memory management
- Network bandwidth

---

### 📊 [Monitoring & Metrics](./monitoring-metrics.md)
Setup monitoring và metrics collection.
- CHƯA TRIỂN KHAI
**Topics**:
- Prometheus integration
- Key metrics to track
- Alert rules
- Dashboard setup (Grafana)

---

### 🐛 [Debugging Guide](./debugging-guide.md)
Các kỹ thuật debug thường dùng.

**Topics**:
- Log analysis
- Thread dumps
- GPU profiling (nvidia-smi, nsight)
- Memory profiling

---

### 🔒 [Security Best Practices](./security.md)
Bảo mật hệ thống trong production.
- CHƯA TRIỂN KHAI
**Topics**:
- Authentication/Authorization
- Network isolation
- Secret management
- Audit logging

---

###  [Deployment Guide](./deployment.md)
Deploy hệ thống lên production.
- CHƯA TRIỂN KHAI
**Topics**:
- Docker setup
- Kubernetes manifests
- Load balancer config
- Rolling updates

---

### 🧪 [Testing Guide](./testing-guide.md)
Chiến lược testing cho hệ thống.

**Topics**:
- Unit tests
- Integration tests
- Load tests
- Chaos engineering

---

## Quick Reference

### Config Parameters

| Parameter | Location | Default | Impact |
|-----------|----------|---------|--------|
| `INFERENCE_MAX_BATCH_SIZE` | config.py | 24 | Throughput, latency |
| `INFERENCE_BATCH_TIMEOUT` | config.py | 1.0s | Latency, batch fill |
| `INFERENCE_NUM_STREAMS` | config.py | 3 | GPU utilization |
| `HEARTBEAT_INTERVAL` | .env | 10s | Network overhead |
| `MODEL_PATH` | config.py | models/*.engine | Model version |

### Performance Targets

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Inference throughput | >300 FPS | <200 FPS |
| GPU utilization | 80-95% | <70% hoặc >98% |
| Frame drop rate | <1% | >5% |
| Inference latency | <50ms | >100ms |
| Camera reconnect rate | <1/hour | >5/hour |

### Log Locations

```
logs/
├── ai_main/log_YYYYMMDD.log
├── camera_processor/log_YYYYMMDD.log
├── inference_engine/log_YYYYMMDD.log
├── pair_manager/log_YYYYMMDD.log
└── worker_manager/log_YYYYMMDD.log
```

### Common Commands

```bash
# Check GPU usage
nvidia-smi -l 1

# Tail logs
tail -f logs/ai_main/log_$(date +%Y%m%d).log

# Check running threads
ps -T -p <pid>

# Memory usage
ps aux | grep python

# Network connections
netstat -an | grep 8000
```

---

[⬅️ Về trang chủ](../README.md) | [➡️ Tiếp: Runbook](../08-runbook/)
