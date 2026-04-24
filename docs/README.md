# Honda AI Monitoring - Documentation

> Comprehensive documentation cho hệ thống Honda AI Monitoring

##  Documentation Structure

### [01. Overview](./01-overview/)
**Dành cho**: Newcomers, stakeholders

Tổng quan về hệ thống - sản phẩm là gì, giải quyết vấn đề gì, use-cases, glossary.

---

###  [02. Architecture](./02-architecture/)
**Dành cho**: Developers, architects

Hiểu hệ thống được thiết kế như thế nào - layers, components, concurrency model, design decisions.

---

###  [03. Flows](./03-flows/)
**Dành cho**: Developers, QA

Hiểu hệ thống chạy như thế nào trong từng use-case - 6 flow documents chi tiết với diagrams.

**Flows**:
1. Worker Registration & Heartbeat
2. Camera Processing (RTSP → Inference)
3. Inference Engine (Batch + CUDA)
4. Pair Management (Start/End + ICS)
5. Streaming API (MJPEG)
6. Camera Control (Enable/Disable)

---

###  [04. Features](./04-features/)
**Dành cho**: Product managers, developers

Hiểu từng chức năng làm gì - capabilities, input/output, configuration.

---

###  [05. API](./05-api/)
**Dành cho**: Frontend developers, integration partners

Service khác hoặc frontend dùng API - endpoints, request/response format, examples.

---

###  [06. Technical](./06-technical/)
**Dành cho**: DevOps, SRE

Docs để maintain/optimize - performance tuning, monitoring, debugging, security.

---

###  [08. Runbook](./08-runbook/)
**Dành cho**: Operators, on-call engineers

Start toàn bộ system + restart từng service + check logs - daily operations.

**Includes**:
- Startup procedures
- Restart procedures
- Distributed failover testing guide
- Camera control test guide

---

###  [09. Troubleshooting](./09-troubleshooting/)
**Dành cho**: Support team, on-call engineers

Fix lỗi nhanh - common issues + cách debug + fix.

---

## Quick Navigation

###  Getting Started
1. [System Overview](./01-overview/system-overview.md) - Hiểu tổng quan
2. [Quick Start](./01-overview/quick-start.md) - Setup lần đầu (coming soon)
3. [Architecture Overview](./02-architecture/README.md) - Hiểu kiến trúc

###  For Developers
1. [Flows Documentation](./03-flows/) - Đọc 6 flows để hiểu hệ thống
2. [Features](./04-features/) - Hiểu từng feature
3. [API Reference](./05-api/) - Tích hợp API

###  For Operations
1. [Runbook](./08-runbook/) - Vận hành daily
2. [Troubleshooting](./09-troubleshooting/) - Fix issues
3. [Technical Docs](./06-technical/) - Performance tuning

###  For Monitoring
1. [Health Checks](./08-runbook/health-checks.md) - Monitor health
2. [Monitoring & Metrics](./06-technical/monitoring-metrics.md) - Setup monitoring
3. [Log Analysis](./08-runbook/log-analysis.md) - Phân tích logs

---

## Documentation Guidelines

### Cập nhật docs
- Mỗi khi thay đổi code có impact đến flow/API → update docs
- Thêm example code khi có thể
- Sử dụng diagrams (ASCII art) cho clarity

### Contributing
- Follow template của từng section
- Code examples phải test được
- Giữ ngôn ngữ đơn giản, dễ hiểu

### Review Process
1. Code change PR → check docs impact
2. Update docs trong cùng PR
3. Review docs như review code

---

## External Links

- **Main README**: [../README.md](../README.md) - Project root README
- **Config**: [../config.py](../config.py) - Runtime config
- **Requirements**: [../requirements.txt](../requirements.txt) - Dependencies
---

**Maintainer**: AI Team | Tesla aka Phương
**Last Major Update**: 2026-04-23  
**Version**: 1.0.0
