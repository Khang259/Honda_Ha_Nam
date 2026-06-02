# MongoDB Cluster Control - Testing Guide

## Mục đích

Testing guide này mô tả cách test các tính năng của MongoDB Cluster Control system sau khi triển khai.

## Chuẩn bị

### 1. Môi trường
- MongoDB replica set đang chạy
- 4 workers (w1, w2, w3, w4) được cấu hình với:
  - `WORKER_ID`: w1, w2, w3, w4
  - `MongoDB_URL`: trỏ đến replica set
  - `AI_SERVER_PORT`: 5000, 5001, 5002, 5003

### 2. Kiểm tra collections
```bash
# MongoDB shell
use HONDA_HN

# Kiểm tra collections tồn tại
db.engine_control_status.find()
db.engine_control_acks.find()
```

### 3. Khởi động workers
```bash
# Terminal 1
cd d:/Project/Honda_Ha_Nam
WORKER_ID=w1 AI_SERVER_PORT=5000 python -m src.apps.main

# Terminal 2
WORKER_ID=w2 AI_SERVER_PORT=5001 python -m src.apps.main

# Terminal 3
WORKER_ID=w3 AI_SERVER_PORT=5002 python -m src.apps.main

# Terminal 4
WORKER_ID=w4 AI_SERVER_PORT=5003 python -m src.apps.main
```

## Test Cases

### Test 1: Bootstrap Test (Worker restart với trạng thái RUN)

**Mục đích**: Verify worker mới start/restart sẽ tự động apply trạng thái hiện tại.

**Steps**:
1. Đảm bảo 4 workers đang chạy
2. Gửi START command:
   ```bash
   curl -X POST http://localhost:5000/engine-control/start-all
   ```
3. Verify response có `token` và `accepted: true`
4. Kiểm tra logs 4 workers thấy "RUN command applied"
5. Stop worker w3
6. Start lại worker w3
7. Kiểm tra log w3 xem có bootstrap và apply RUN không

**Expected**:
- Worker w3 log: `Bootstrap: current cluster state=RUN, token=X`
- Worker w3 log: `Applying RUN command (token=X)`
- Worker w3 cameras start lại

**Verify**:
```bash
# Check w3 applied
curl http://localhost:5002/engine-control/cameras-enable-state
# Should show cameras enabled

# Check ack in MongoDB
db.engine_control_acks.find({worker_id: "w3"})
```

---

### Test 2: Change Stream Test (Real-time propagation)

**Mục đích**: Verify change stream lan truyền lệnh đến tất cả workers ngay lập tức.

**Steps**:
1. Đảm bảo 4 workers đang chạy và ở trạng thái STOP
2. Mở 4 terminal để tail logs:
   ```bash
   tail -f logs/cluster_control_listener/log_*.log
   ```
3. Gửi START command:
   ```bash
   time curl -X POST http://localhost:5000/engine-control/start-all
   ```
4. Quan sát logs 4 workers

**Expected**:
- Response trả về ngay với `token` mới (< 100ms)
- Trong vòng 1-2s, cả 4 workers log "Applying RUN command"
- Không có worker nào bỏ lỡ lệnh

**Verify**:
```bash
# Check cluster status
curl http://localhost:5000/engine-control/cluster-status | python -m json.tool

# Should show:
# - desired_state: "RUN"
# - acks_count: 4
# - All 4 workers in acks array
```

---

### Test 3: Fallback Poll Test (Change stream unavailable)

**Mục đích**: Verify hệ thống vẫn hoạt động khi change stream bị lỗi (fallback polling).

**Steps**:
1. Tạm stop MongoDB replica set hoặc downgrade về standalone
2. Restart một worker (sẽ không có change stream)
3. Kiểm tra logs thấy: `Change stream unavailable ... falling back to polling`
4. Gửi STOP command:
   ```bash
   curl -X POST http://localhost:5000/engine-control/stop-all
   ```
5. Chờ 2-4 giây (polling interval)
6. Verify worker đã apply STOP

**Expected**:
- Worker log: `falling back to polling`
- Worker log: `Poll detected new command: state=STOP`
- Cameras stop trong vòng 2-4s

**Note**: Test này khó setup trên production. Có thể test bằng cách:
- Tắt replica set tạm thời
- Hoặc comment out change stream code để force polling

---

### Test 4: Token Ordering Test (START → STOP → START nhanh)

**Mục đích**: Verify token đảm bảo lệnh mới nhất được apply đúng.

**Steps**:
1. Setup: 4 workers đang chạy, trạng thái STOP
2. Gửi 3 lệnh liên tiếp:
   ```bash
   curl -X POST http://localhost:5000/engine-control/start-all
   sleep 0.5
   curl -X POST http://localhost:5000/engine-control/stop-all
   sleep 0.5
   curl -X POST http://localhost:5000/engine-control/start-all
   ```
3. Chờ 2 giây
4. Kiểm tra trạng thái cuối

**Expected**:
- Lệnh cuối cùng (START) thắng
- All workers ở trạng thái RUN
- Token tăng 3 lần (ví dụ: 1001 → 1002 → 1003)

**Verify**:
```bash
# Check final state
curl http://localhost:5000/engine-control/cluster-status | python -m json.tool

# Should show:
# - desired_state: "RUN"
# - token: 1003 (hoặc giá trị cao nhất)
# - acks_count: 4

# Check MongoDB
db.engine_control_status.find()
db.engine_control_acks.find().sort({token: -1}).limit(10)
```

---

### Test 5: Partial Failure Test (Worker down)

**Mục đích**: Verify hệ thống hoạt động khi một worker bị down.

**Steps**:
1. Stop worker w3 (kill process)
2. Gửi START command:
   ```bash
   curl -X POST http://localhost:5000/engine-control/start-all
   ```
3. Verify 3 workers còn lại apply thành công
4. Start lại w3
5. Verify w3 tự động catch up

**Expected**:
- 3 workers (w1, w2, w4) apply ngay
- `acks_count` = 3
- Khi w3 lên lại, bootstrap → apply → `acks_count` = 4

**Verify**:
```bash
# Before w3 restart
curl http://localhost:5000/engine-control/cluster-status | python -m json.tool
# acks_count: 3

# After w3 restart (wait 2s)
curl http://localhost:5000/engine-control/cluster-status | python -m json.tool
# acks_count: 4
```

---

### Test 6: Dedupe Test (Worker nhận POST không apply 2 lần)

**Mục đích**: Verify worker nhận HTTP request không chạy local + qua listener (double apply).

**Steps**:
1. Gửi START qua worker w1:
   ```bash
   curl -X POST http://localhost:5001/engine-control/start-all
   ```
2. Kiểm tra log w1 chi tiết
3. Count số lần "Applying RUN command" xuất hiện

**Expected**:
- Worker w1 chỉ apply **1 lần** (qua listener, không qua HTTP handler)
- Log không có duplicate "Applying RUN command (token=X)"

**Verify logs**:
```bash
grep "Applying RUN command" logs/cluster_control_listener/log_*.log | grep "w1"
# Should appear exactly once for the token
```

---

### Test 7: Zone Routes Unchanged

**Mục đích**: Verify zone-specific routes vẫn hoạt động local (không qua Mongo).

**Steps**:
1. Gửi zone start:
   ```bash
   curl -X POST http://localhost:5000/engine-control/AE5/start-all
   ```
2. Kiểm tra chỉ worker đó (hoặc workers có camera zone AE5) start
3. Verify không có document mới trong `engine_control_status`

**Expected**:
- Zone routes gọi trực tiếp `camera_manager.set_zone_enabled()` local
- Không tạo cluster command
- Token không tăng

---

## Monitoring Commands

### Check current cluster state
```bash
curl http://localhost:5000/engine-control/cluster-status | python -m json.tool
```

### Check MongoDB collections
```javascript
// Status document
db.engine_control_status.find().pretty()

// Recent acks
db.engine_control_acks.find().sort({applied_at_utc: -1}).limit(20).pretty()

// Acks for specific token
db.engine_control_acks.find({token: 1002})

// Count acks per token
db.engine_control_acks.aggregate([
  {$group: {_id: "$token", count: {$sum: 1}}},
  {$sort: {_id: -1}}
])
```

### Check logs
```bash
# Cluster listener logs
tail -f logs/cluster_control_listener/log_*.log

# Mongo client logs
tail -f logs/mongo_cluster_control_client/log_*.log

# Engine control routes logs
tail -f logs/engine_control_routes/log_*.log
```

---

## Expected Behaviors

### Normal Flow (4 workers healthy)
1. POST /start-all → response < 100ms
2. Token increment atomic
3. All 4 workers apply within 1-2s
4. All 4 acks written to MongoDB
5. GET /cluster-status shows acks_count=4

### Worker Restart Flow
1. Worker stops
2. Worker starts → bootstrap reads status
3. If token newer → apply immediately
4. Write ack
5. Continue listening

### Poll Fallback Flow
1. Change stream error detected
2. Log: "falling back to polling"
3. Poll every 2s
4. Apply on token change
5. Latency increases to 2-4s (acceptable)

---

## Troubleshooting

### Issue: Worker không apply lệnh
**Check**:
- Worker log có "Bootstrap" message?
- Worker log có "Change detected" hoặc "Poll detected"?
- `last_applied_token` value trong log?
- MongoDB document có tồn tại?

### Issue: Acks count < 4
**Check**:
- Tất cả workers có đang chạy? (`ps aux | grep python`)
- Workers có lỗi trong log?
- MongoDB connection OK?
- Collection `engine_control_acks` có unique index không?

### Issue: Token không tăng
**Check**:
- Route có gọi `update_desired_state()` đúng không?
- MongoDB có lỗi khi `$inc`?
- Check log `mongo_cluster_control_client`

---

## Success Criteria

Tất cả tests pass nếu:
- ✅ Bootstrap test: Worker restart tự apply đúng state
- ✅ Change stream: 4 workers apply trong < 2s
- ✅ Poll fallback: Worker vẫn hoạt động khi no change stream
- ✅ Token ordering: Lệnh cuối luôn thắng
- ✅ Partial failure: Worker down/up không ảnh hưởng cluster
- ✅ Dedupe: Worker nhận POST chỉ apply 1 lần
- ✅ Zone routes: Vẫn hoạt động local

## Notes

- Test trên local dev: có thể chạy 4 workers trên cùng máy với ports khác nhau
- Test trên staging/prod: cần 4 máy riêng biệt hoặc containers
- MongoDB replica set bắt buộc cho change stream (hoặc chỉ test polling mode)
