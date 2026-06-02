# MongoDB Cluster Control Implementation Summary

## Tổng quan

Đã triển khai thành công MongoDB Cluster Control system cho phép điều khiển cả 4 workers chỉ với một lần POST request từ Frontend. System sử dụng MongoDB pub/sub pattern với change stream và fallback polling để đồng bộ lệnh start/stop across cluster.

## Các files đã tạo mới

### 1. `src/persistence/mongo/mongo_cluster_control_client.py`
MongoDB client quản lý 2 collections:
- **engine_control_status**: Lưu trạng thái mong muốn (desired_state) và token
- **engine_control_acks**: Lưu acknowledgments từ mỗi worker

**Methods chính**:
- `update_desired_state(state, updated_by_worker)`: Ghi lệnh cluster + increment token atomically
- `get_current_status()`: Đọc trạng thái hiện tại
- `write_ack(worker_id, token, applied_state)`: Ghi ack sau khi worker apply
- `get_acks(token)`: Lấy danh sách acks cho token cụ thể

### 2. `src/coordination/cluster_control_listener.py`
Background service chạy trên mỗi worker để listen MongoDB changes.

**Tính năng**:
- **Bootstrap**: Khi worker start, đọc status hiện tại và apply nếu token mới
- **Change stream**: Real-time listening MongoDB changes (< 1s latency)
- **Fallback polling**: Tự động chuyển sang poll mỗi 2s nếu change stream lỗi
- **Dedupe**: Sử dụng `last_applied_token` để tránh apply lệnh đã xử lý
- **Apply logic**: Gọi camera_manager, inference_engine, pairing_orchestrator
- **Ack writing**: Ghi ack vào MongoDB sau khi apply thành công

### 3. `docs/08-runbook/CLUSTER_CONTROL_TESTING.md`
Comprehensive testing guide với 7 test cases chi tiết.

## Các files đã sửa đổi

### 1. `src/api_http/routes/cameras.py`

**Thay đổi POST /engine-control/start-all**:
```python
# Trước: Gọi local
api_state.camera_manager.start_all_cameras()
api_state.inference_engine.resume()

# Sau: Ghi MongoDB
client = MongoClusterControlClient()
result = await client.update_desired_state("RUN", settings.WORKER_ID)
return {"accepted": True, "token": result["token"], ...}
```

**Thay đổi POST /engine-control/stop-all**: Tương tự

**Thêm GET /engine-control/cluster-status**:
- Trả về current desired_state, token, timestamp
- Trả về list acks từ workers
- Trả về acks_count để verify 4/4 workers đã apply

### 2. `src/runtime/runtime_service.py`

**start() method**:
- Khởi tạo `ClusterControlListener` sau khi tất cả components ready
- Start listener task trong background
- Add vào `_components` dict

**stop() method**:
- Stop listener gracefully
- Cancel listener task
- Cleanup references

## Schema MongoDB

### Collection: engine_control_status
```json
{
  "_id": "inference_status",
  "desired_state": "RUN",
  "token": 1002,
  "updated_by_worker": "w1",
  "timestamp": "2026-06-02 14:30:00",
  "timestamp_utc": ISODate("2026-06-02T07:30:00Z")
}
```

### Collection: engine_control_acks
```json
{
  "worker_id": "w3",
  "token": 1002,
  "applied_state": "RUN",
  "applied_at": "2026-06-02 14:30:01",
  "applied_at_utc": ISODate("2026-06-02T07:30:01Z")
}
```

**Index cần tạo**:
```javascript
db.engine_control_acks.createIndex({worker_id: 1, token: 1}, {unique: true})
```

## Luồng hoạt động

### Flow 1: Normal Start-All Command

```
1. Frontend → POST /engine-control/start-all (bất kỳ worker)
2. Worker X → MongoDB.findOneAndUpdate:
   - Set desired_state = "RUN"
   - Increment token (1001 → 1002)
3. MongoDB → Response: {token: 1002, desired_state: "RUN"}
4. Worker X → Return to Frontend: {accepted: true, token: 1002}

5. MongoDB change stream → Broadcast to all 4 workers
6. Each worker:
   - Check: token (1002) > last_applied_token (1001) → Yes
   - Apply RUN:
     * camera_manager.start_all_cameras()
     * inference_engine.resume()
     * pairing_orchestrator.resume()
   - Update: last_applied_token = 1002
   - Write ack to MongoDB

7. Result: All 4 workers running, 4 acks in MongoDB
```

### Flow 2: Worker Restart (Bootstrap)

```
1. Worker w3 starts up
2. RuntimeService.start() → Initialize all components
3. Start ClusterControlListener
4. Listener.bootstrap():
   - MongoDB.findOne({_id: "inference_status"})
   - Read: {desired_state: "RUN", token: 1002}
   - Check: token (1002) > last_applied_token (-1) → Yes
   - Apply RUN immediately
   - Write ack

5. Worker w3 now in sync with cluster
```

### Flow 3: Change Stream Fallback

```
1. Change stream connection fails (replica set issue)
2. Listener logs: "Change stream unavailable; falling back to polling"
3. Start polling loop (every 2s):
   - MongoDB.findOne({_id: "inference_status"})
   - Compare token with last_applied_token
   - If newer → apply

4. Latency increases to 2-4s (acceptable for fallback)
```

## Kiến trúc hệ thống

```
┌─────────────────────────────────────────────────────┐
│                    Frontend/UI                       │
└────────────────────┬────────────────────────────────┘
                     │ POST /start-all (1 lần)
                     ▼
┌─────────────────────────────────────────────────────┐
│            Worker (bất kỳ) - HTTP Handler           │
│  MongoClusterControlClient.update_desired_state()   │
└────────────────────┬────────────────────────────────┘
                     │ Write + $inc token
                     ▼
┌─────────────────────────────────────────────────────┐
│              MongoDB (Coordination)                  │
│  Collection: engine_control_status                   │
│  {desired_state: "RUN", token: 1002}                │
└──┬──────────────────┬──────────────────┬────────────┘
   │ stream           │ stream           │ stream
   ▼                  ▼                  ▼
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ Worker 1 │   │ Worker 2 │   │ Worker 3 │   │ Worker 4 │
│ Listener │   │ Listener │   │ Listener │   │ Listener │
└────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘
     │              │              │              │
     ▼              ▼              ▼              ▼
  Apply RUN     Apply RUN     Apply RUN     Apply RUN
     │              │              │              │
     └──────────────┴──────────────┴──────────────┘
                     │ Write acks
                     ▼
┌─────────────────────────────────────────────────────┐
│              MongoDB (Tracking)                      │
│  Collection: engine_control_acks                     │
│  [{worker_id: "w1", token: 1002}, ...]              │
└─────────────────────────────────────────────────────┘
```

## Ưu điểm của implementation

1. **Decentralized**: Không có master worker, tất cả workers bình đẳng
2. **Resilient**: Worker down/restart tự động sync qua bootstrap
3. **Low latency**: Change stream < 1-2s cho normal case
4. **Fault tolerant**: Fallback polling khi change stream lỗi
5. **Eventually consistent**: Worker chậm sẽ catch up
6. **Observable**: GET /cluster-status cho thấy trạng thái + acks
7. **Simple Frontend**: FE chỉ gọi 1 endpoint, không cần biết có bao nhiêu workers
8. **Idempotent**: Start/stop nhiều lần không gây side-effects

## Trade-offs

1. **Không phải instant 4/4**: Có độ trễ 1-2s (hoặc 2-4s nếu polling)
2. **Cần replica set**: Change stream yêu cầu MongoDB replica set
3. **Eventual consistency**: Không đảm bảo 4/4 áp dụng đồng thời 100%
4. **Phụ thuộc MongoDB**: Control plane phụ thuộc vào DB availability

## Cách sử dụng

### Frontend/Client

```javascript
// Start all workers
const response = await fetch('http://vip-endpoint/engine-control/start-all', {
  method: 'POST'
});
const data = await response.json();
// {accepted: true, token: 1002, desired_state: "RUN"}

// Check status
const status = await fetch('http://vip-endpoint/engine-control/cluster-status');
const statusData = await status.json();
// {
//   status: {desired_state: "RUN", token: 1002},
//   acks: [{worker_id: "w1", ...}, ...],
//   acks_count: 4
// }
```

### Monitoring

```bash
# Check current cluster state
curl http://localhost:5000/engine-control/cluster-status | jq .

# Check MongoDB
mongosh
> use HONDA_HN
> db.engine_control_status.find().pretty()
> db.engine_control_acks.find().sort({applied_at_utc: -1}).pretty()

# Check logs
tail -f logs/cluster_control_listener/log_*.log
tail -f logs/mongo_cluster_control_client/log_*.log
```

## Tiếp theo (Optional enhancements)

Những tính năng có thể thêm sau:

1. **TTL cho acks**: Auto-delete acks cũ sau 7 ngày
2. **Health check endpoint**: GET /cluster-health với expected vs actual acks
3. **Retry logic**: Worker tự retry nếu apply thất bại
4. **Zone-level cluster commands**: POST /cluster/AE5/start-all
5. **Command history**: Log lịch sử commands với timestamp
6. **Metrics**: Prometheus metrics cho latency, ack counts
7. **Alert**: Slack/email notification khi acks_count < expected

## Kết luận

Implementation đã hoàn thành đầy đủ các yêu cầu:
- ✅ Một lần POST từ FE → 4 workers thực thi
- ✅ MongoDB pub/sub pattern với change stream
- ✅ Fallback polling khi change stream lỗi
- ✅ Bootstrap khi worker restart
- ✅ Token-based ordering cho STOP/START liên tiếp
- ✅ Ack tracking để biết 4/4 workers đã apply
- ✅ Decentralized architecture không cần master

Hệ thống sẵn sàng để test theo guide trong `CLUSTER_CONTROL_TESTING.md`.
