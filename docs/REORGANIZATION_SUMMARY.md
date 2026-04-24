# Documentation Reorganization Summary

## 📂 Cấu trúc mới

```
docs/
├── README.md                    # Index tổng hợp
│
├── 01-overview/                 # Tổng quan hệ thống
│   ├── README.md
│   ├── system-overview.md       # Mô tả chi tiết hệ thống
│   ├── quick-start.md           # Hướng dẫn setup nhanh
│   └── glossary.md              # Thuật ngữ
│
├── 02-architecture/             # Kiến trúc
│   └── README.md                # Overview kiến trúc
│       (TODO: system-architecture.md, concurrency-model.md, ...)
│
├── 03-flows/                    # Luồng hoạt động
│   ├── README.md
│   ├── 01_worker_registration_heartbeat_flow.md
│   ├── 02_camera_processing_flow.md
│   ├── 03_inference_engine_flow.md
│   ├── 04_pair_management_flow.md
│   ├── 05_streaming_api_flow.md
│   └── 06_camera_control_flow.md
│
├── 04-features/                 # Chức năng
│   └── README.md                # Feature matrix
│       (TODO: camera-management.md, ai-inference.md, ...)
│
├── 05-api/                      # API Documentation
│   └── README.md                # API overview + examples
│       (TODO: health-status.md, camera-control.md, ...)
│
├── 06-technical/                # Technical docs
│   └── README.md                # Technical overview
│       (TODO: performance-tuning.md, monitoring.md, ...)
│
├── 08-runbook/                  # Vận hành
│   ├── README.md
│   ├── DISTRIBUTED_FAILOVER_TESTING.md
│   └── CAMERA_CONTROL_TEST_GUIDE.md
│       (TODO: startup-procedure.md, restart-procedures.md, ...)
│
└── 09-troubleshooting/          # Fix lỗi
    └── README.md                # Common issues + fixes
        (TODO: service-wont-start.md, gpu-oom.md, ...)
```

## 📋 Files đã di chuyển

| File cũ | → | Vị trí mới |
|---------|---|------------|
| `docs/01-06_*_flow.md` | → | `docs/03-flows/` |
| `DISTRIBUTED_FAILOVER_TESTING.md` | → | `docs/08-runbook/` |
| `CAMERA_CONTROL_TEST_GUIDE.md` | → | `docs/08-runbook/` |

## ✅ Files đã tạo mới

### 01-overview/
- ✅ `README.md` - Navigation
- ✅ `system-overview.md` - Tổng quan chi tiết
- ✅ `quick-start.md` - Setup guide
- ✅ `glossary.md` - Thuật ngữ

### 02-09/ (Structure only)
- ✅ README.md cho từng folder
- 🚧 Detailed docs (TODO - template đã có)

## 🎯 Mục đích từng folder

| Folder | Dành cho | Mục đích |
|--------|----------|----------|
| **01-overview** | Newcomers, stakeholders | Hiểu "là gì" và "tại sao" |
| **02-architecture** | Developers, architects | Hiểu "thiết kế như thế nào" |
| **03-flows** | Developers, QA | Hiểu "chạy như thế nào" |
| **04-features** | Product managers, devs | Hiểu "tính năng làm gì" |
| **05-api** | Frontend, integration | Hiểu "dùng API như thế nào" |
| **06-technical** | DevOps, SRE | Hiểu "maintain/optimize" |
| **08-runbook** | Operators, on-call | Hiểu "vận hành daily" |
| **09-troubleshooting** | Support, on-call | Hiểu "fix lỗi nhanh" |

## 📝 Navigation Hierarchy

```
docs/README.md (Entry point)
    ├─> 01-overview/README.md
    │   ├─> system-overview.md
    │   ├─> quick-start.md
    │   └─> glossary.md
    │
    ├─> 02-architecture/README.md
    │   └─> (TODO: chi tiết docs)
    │
    ├─> 03-flows/README.md
    │   ├─> 01_worker_*.md
    │   ├─> 02_camera_*.md
    │   └─> ...
    │
    └─> ... (tương tự)
```

## 🚧 TODO (Đề xuất nội dung tiếp theo)

### High Priority

#### 02-architecture/
- [ ] `system-architecture.md` - Detailed architecture với diagrams
- [ ] `concurrency-model.md` - Threads/async model chi tiết
- [ ] `data-model.md` - MongoDB schema reference

#### 05-api/
- [ ] `health-status.md` - Health check API details
- [ ] `camera-control.md` - Camera control API + examples
- [ ] `streaming.md` - Streaming API + browser examples

#### 06-technical/
- [ ] `performance-tuning.md` - Tuning guide với benchmarks
- [ ] `monitoring-metrics.md` - Prometheus/Grafana setup

#### 08-runbook/
- [ ] `startup-procedure.md` - Step-by-step startup
- [ ] `health-checks.md` - Daily check checklist

#### 09-troubleshooting/
- [ ] `service-wont-start.md` - Common startup issues
- [ ] `gpu-oom.md` - GPU memory troubleshooting
- [ ] `camera-reconnect.md` - Camera connection issues

### Medium Priority

#### 04-features/
- [ ] Feature-specific docs (1 file per feature)
- [ ] Configuration reference per feature

#### 06-technical/
- [ ] `debugging-guide.md` - Advanced debugging
- [ ] `security.md` - Security best practices
- [ ] `deployment.md` - Production deployment guide

### Low Priority (Nice to have)

- [ ] Video tutorials / screenshots
- [ ] Architecture decision records (ADRs)
- [ ] Performance benchmark results
- [ ] Migration guides (version upgrades)

## 💡 Best Practices khi thêm docs mới

### 1. Chọn đúng folder
- **Overview**: Khái niệm tổng quan, use-case
- **Architecture**: Design, patterns, technical decisions
- **Flows**: Sequence diagrams, step-by-step processes
- **Features**: Feature capabilities, input/output
- **API**: Endpoints, request/response format
- **Technical**: Tuning, debugging, monitoring
- **Runbook**: Procedures, checklists
- **Troubleshooting**: Symptoms → diagnosis → fix

### 2. Template docs
Mỗi doc nên có:
- **Title + Subtitle**: Rõ ràng mục đích
- **Prerequisites**: Kiến thức/setup cần trước
- **Main Content**: Có examples/diagrams
- **See Also**: Link tới docs liên quan
- **Navigation**: Links về parent/sibling docs

### 3. Formatting
- Dùng headers (##, ###) để phân cấp
- Code blocks có syntax highlight
- ASCII diagrams cho data flow
- Tables cho comparison/reference
- Bullets cho checklists

### 4. Maintenance
- Update docs khi code change
- Thêm "Last Updated" date
- Version docs nếu có breaking changes
- Review docs như review code

## 📖 How to Read

### Nếu bạn là...

**New Team Member**:
1. Start: `01-overview/system-overview.md`
2. Setup: `01-overview/quick-start.md`
3. Deep dive: `03-flows/` (đọc tất cả 6 flows)

**Developer (Feature Development)**:
1. Understand: `02-architecture/` + `03-flows/`
2. Reference: `04-features/` + `05-api/`
3. Test: `08-runbook/` testing guides

**Operator (Daily Operations)**:
1. Operations: `08-runbook/`
2. Issues: `09-troubleshooting/`
3. Reference: `05-api/` (health checks)

**DevOps/SRE**:
1. Deploy: `06-technical/deployment.md` (TODO)
2. Monitor: `06-technical/monitoring-metrics.md` (TODO)
3. Tune: `06-technical/performance-tuning.md` (TODO)

## 🔗 External Links

- [Main README](../README.md) - Project root
- [AGENTS.md](../AGENTS.md) - Agent rules
- [config.py](../config.py) - Runtime config

---

**Created**: 2026-04-23  
**Last Updated**: 2026-04-23  
**Maintainer**: AI Team
