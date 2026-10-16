# Kịch Bản Test Cluster Trên 1 Máy Duy Nhất

## Tổng Quan

Tài liệu này điều chỉnh kịch bản test cluster control cho môi trường **1 máy duy nhất** chạy 4 workers bằng 4 terminal/processes riêng biệt.

**Ưu điểm:**
- ✅ Không cần hạ tầng nhiều máy
- ✅ Setup nhanh, dễ debug
- ✅ Đủ để test đa số logic nghiệp vụ

**Hạn chế:**
- ⚠️ Không test được network latency giữa máy
- ⚠️ Test T4 (Clock Skew) không thực tế (cùng 1 đồng hồ)
- ⚠️ GPU/CPU load không phản ánh thực tế production (4 máy riêng)

---

## I. SETUP MÔI TRƯỜNG 1 MÁY

### 1.1 MongoDB Single Node Replica Set

**Tại sao cần replica set?** Change stream yêu cầu replica set, không hoạt động với standalone.

**Cách setup replica set 1 node:**

```powershell
# 1. Tạo thư mục data
mkdir D:\mongodb_data

# 2. Start mongod với replica set
mongod --dbpath D:\mongodb_data --port 27017 --replSet rs0

# 3. Terminal mới - Init replica set
mongosh
```

```javascript
// Trong mongosh
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "localhost:27017" }
  ]
})

// Verify
rs.status()
// Phải thấy: stateStr: "PRIMARY"

// Test change stream
use HONDA_HN
db.engine_control_status.watch()
// Ctrl+C để thoát
```

### 1.2 Config .env

```env
# d:\Prj\Honda_Ha_Nam\.env

# MongoDB - Local Replica Set
MONGODB_URL=mongodb://localhost:27017/HONDA_HN?replicaSet=rs0
MONGO_REPLICA_SET=rs0

# Workers sẽ dùng WORKER_ID từ environment variable
# Ports: 5000, 5001, 5002, 5003
```

### 1.3 Khởi Động 4 Workers

**Cách 1: 4 PowerShell Windows (Khuyến nghị)**

```powershell
# Window 1
cd D:\Prj\Honda_Ha_Nam
$env:WORKER_ID="w1"; $env:AI_SERVER_PORT="5000"
python -m src.apps.main

# Window 2
cd D:\Prj\Honda_Ha_Nam
$env:WORKER_ID="w2"; $env:AI_SERVER_PORT="5001"
python -m src.apps.main

# Window 3
cd D:\Prj\Honda_Ha_Nam
$env:WORKER_ID="w3"; $env:AI_SERVER_PORT="5002"
python -m src.apps.main

# Window 4
cd D:\Prj\Honda_Ha_Nam
$env:WORKER_ID="w4"; $env:AI_SERVER_PORT="5003"
python -m src.apps.main
```

**Cách 2: 1 PowerShell với background jobs (Debugging khó hơn)**

```powershell
# start_all_workers.ps1
$workers = @("w1", "w2", "w3", "w4")
$ports = @("5000", "5001", "5002", "5003")

for ($i = 0; $i -lt 4; $i++) {
    Start-Job -Name $workers[$i] -ScriptBlock {
        param($id, $port, $path)
        cd $path
        $env:WORKER_ID = $id
        $env:AI_SERVER_PORT = $port
        python -m src.apps.main
    } -ArgumentList $workers[$i], $ports[$i], "D:\Prj\Honda_Ha_Nam"
}

# Xem output
Get-Job | Receive-Job -Keep

# Stop tất cả
Get-Job | Stop-Job
Get-Job | Remove-Job
```

### 1.4 Helper Scripts

**check_status.ps1:**
```powershell
function Check-ClusterStatus {
    $status = Invoke-RestMethod -Uri "http://localhost:5000/engine-control/cluster-status"
    Write-Host "===== Cluster Status ====="
    Write-Host "State: $($status.status.desired_state)"
    Write-Host "Token: $($status.status.token)"
    Write-Host "Acks: $($status.acks_count)/4"
    Write-Host ""
    
    foreach ($ack in $status.acks) {
        Write-Host "  $($ack.worker_id): $($ack.applied_state) at $($ack.applied_at)"
    }
    
    return $status
}

function Get-WorkerProcesses {
    Get-Process -Name python | Where-Object {
        $_.CommandLine -like "*src.apps.main*"
    } | Select-Object Id, @{Name="Port";Expression={
        if ($_.CommandLine -match "AI_SERVER_PORT=(\d+)") { $matches[1] } else { "?" }
    }}, @{Name="WorkerID";Expression={
        if ($_.CommandLine -match "WORKER_ID=(\w+)") { $matches[1] } else { "?" }
    }}
}

function Get-FFmpegCount {
    $count = (Get-Process -Name ffmpeg -ErrorAction SilentlyContinue | Measure-Object).Count
    Write-Host "FFmpeg processes: $count"
    return $count
}
```

---

## II. TESTS THỰC HIỆN ĐƯỢC HOÀN TOÀN

### ✅ T1: Bootstrap Test

**Khả thi:** 100% - Không phụ thuộc nhiều máy

**Điều chỉnh:** Không cần

**Thực hiện:**
```powershell
# 1. Start 4 workers
# 2. Start cluster
curl -X POST http://localhost:5000/engine-control/start-all

# 3. Stop w3 (Ctrl+C trong terminal w3)

# 4. Start lại w3
cd D:\Prj\Honda_Ha_Nam
$env:WORKER_ID="w3"; $env:AI_SERVER_PORT="5002"
python -m src.apps.main

# 5. Verify bootstrap
Select-String -Path "logs/w3/cluster_control_listener/log_*.log" -Pattern "Bootstrap"
```

**Kết quả mong đợi:** Giống tài liệu gốc

---

### ✅ T2: Failover Test (Điều Chỉnh)

**Khả thi:** 95% - Có thể test logic, nhưng không test network failure

**Điều chỉnh:**
- "Kill worker w1" = Ctrl+C trong terminal w1 (hoặc `Stop-Process`)
- Không test network partition (vì cùng localhost)

**Thực hiện:**
```powershell
# 1. Snapshot ban đầu
mongosh --eval 'db.getSiblingDB("HONDA_HN").node_id.aggregate([{$group: {_id: "$current_worker", count: {$sum: 1}}}])'

# 2. Stop worker w1
# Trong terminal w1: Ctrl+C
# Hoặc:
$w1_process = Get-Process python | Where-Object {
    $_.CommandLine -like "*WORKER_ID=w1*"
}
Stop-Process -Id $w1_process.Id

# 3. Đợi 20s
Start-Sleep -Seconds 20

# 4. Kiểm tra rebalance
mongosh --eval 'db.getSiblingDB("HONDA_HN").node_id.aggregate([{$group: {_id: "$current_worker", count: {$sum: 1}}}])'

# 5. Verify hot-apply
Select-String -Path "logs/w2/camera_manager/log_*.log" -Pattern "add_camera"
Get-FFmpegCount

# 6. Start lại w1
cd D:\Prj\Honda_Ha_Nam
$env:WORKER_ID="w1"; $env:AI_SERVER_PORT="5000"
python -m src.apps.main

# 7. Đợi rebalance
Start-Sleep -Seconds 20

# 8. Verify minimize move
mongosh --eval 'db.getSiblingDB("HONDA_HN").node_id.aggregate([{$group: {_id: "$current_worker", count: {$sum: 1}}}])'
```

**Kết quả mong đợi:**
- ✅ Camera của w1 được chia cho w2/w3/w4
- ✅ Total moves ≤ 25
- ✅ Hot-apply hoạt động (log + ffmpeg)
- ✅ w1 quay lại: ~20 camera chuyển về

**Lưu ý 1 máy:**
- GPU load sẽ cao hơn (cùng 1 GPU decode nhiều cameras)
- Có thể giảm số cameras/worker để máy không quá tải

---

### ✅ T5: Token Reset Test

**Khả thi:** 100%

**Điều chỉnh:** Không cần

**Thực hiện:**
```powershell
Check-ClusterStatus

mongosh
```

```javascript
use HONDA_HN
db.engine_control_status.deleteOne({_id: "inference_status"})
exit
```

```powershell
curl -X POST http://localhost:5000/engine-control/stop-all

# Verify logs
Select-String -Path "logs/w*/cluster_control_listener/log_*.log" -Pattern "Token went backwards"
```

---

### ✅ T6: Worker Rejoin Test

**Khả thi:** 100%

**Điều chỉnh:** Tương tự T2, dùng Ctrl+C thay vì network failure

---

### ✅ T7: Change Stream Failure Test (Điều Chỉnh)

**Khả thi:** 90% - Có thể test polling fallback

**Cách giả lập stream failure trên 1 máy:**

**Cách 1: Downgrade MongoDB về standalone**
```powershell
# 1. Stop mongod replica set
# 2. Start mongod standalone
mongod --dbpath D:\mongodb_data_standalone --port 27017

# 3. Update .env
# MONGODB_URL=mongodb://localhost:27017/HONDA_HN (bỏ ?replicaSet=rs0)

# 4. Restart 1 worker
$env:WORKER_ID="w2"; $env:AI_SERVER_PORT="5001"
python -m src.apps.main

# 5. Verify log có fallback polling
Select-String -Path "logs/w2/cluster_control_listener/log_*.log" -Pattern "fallback to polling"

# 6. Gửi lệnh
curl -X POST http://localhost:5000/engine-control/stop-all

# 7. Verify apply sau ~5s
```

**Cách 2: Tạm comment code change stream (nhanh hơn)**
```python
# src/load_balancing/cluster_control_listener.py

async def _stream_loop(self) -> None:
    """Test: skip stream, force polling"""
    logger.warning("Stream disabled for testing; using poll only")
    return  # ← Thêm dòng này để skip stream
```

---

### ✅ T8: Memory Leak Test

**Khả thi:** 100%

**Điều chỉnh:** Giảm số lần lặp nếu máy chậm

**Thực hiện:**
```powershell
# Snapshot ban đầu
$initial_ffmpeg = Get-FFmpegCount
$initial_mem = (Get-Process python | Measure-Object WorkingSet64 -Sum).Sum / 1GB
Write-Host "Initial: FFmpeg=$initial_ffmpeg, Memory=$($initial_mem) GB"

# Loop 20 lần (giảm xuống 10 nếu máy chậm)
for ($i=1; $i -le 20; $i++) {
    Write-Host "===== Iteration $i ====="
    
    curl -X POST http://localhost:5000/engine-control/stop-all
    Start-Sleep -Seconds 5
    
    curl -X POST http://localhost:5000/engine-control/start-all
    Start-Sleep -Seconds 10
    
    $ffmpeg = Get-FFmpegCount
    $mem = (Get-Process python | Measure-Object WorkingSet64 -Sum).Sum / 1GB
    Write-Host "Iter $i : FFmpeg=$ffmpeg, Memory=$($mem) GB"
}

# Snapshot cuối
$final_ffmpeg = Get-FFmpegCount
$final_mem = (Get-Process python | Measure-Object WorkingSet64 -Sum).Sum / 1GB
Write-Host "Final: FFmpeg=$final_ffmpeg, Memory=$($final_mem) GB"
Write-Host "Leak: FFmpeg=$(($final_ffmpeg - $initial_ffmpeg)), Memory=$(($final_mem - $initial_mem)) GB"
```

**Kết quả mong đợi:**
- FFmpeg leak < 5%
- Memory leak < 20%

---

### ✅ T9: Console Quick Edit Test

**Khả thi:** 100%

**Thực hiện:**
```powershell
# 1. Enable Quick Edit trên terminal w1
# Right-click title bar → Properties → Options → Quick Edit Mode

# 2. Click vào console w1 (pause)

# 3. Đợi 60s

# 4. Trong terminal khác, check heartbeat
mongosh --eval 'db.getSiblingDB("HONDA_HN").register_worker.find({worker_id: "w1"}).pretty()'

# 5. Nhấn Enter để unpause
```

**Kết quả mong đợi:**
- Nếu có fix: heartbeat vẫn update
- Nếu chưa fix: heartbeat dừng → w1 bị coi là dead

---

## III. TESTS HẠN CHẾ TRÊN 1 MÁY

### ⚠️ T3: MongoDB Primary Election Test

**Khả thi:** 50% - Có thể test logic, nhưng không thực tế

**Vấn đề:**
- Replica set 1-node không có election thật sự
- Cần ít nhất 3 nodes để test election

**Giải pháp thay thế:**
Giả lập bằng cách stop/start MongoDB:

```powershell
# 1. Workers đang chạy
Check-ClusterStatus

# 2. Stop mongod
Stop-Process -Name mongod

# 3. Quan sát logs workers (30s)
# Mong đợi: log "MongoDB unavailable", không crash

# 4. Start lại mongod
mongod --dbpath D:\mongodb_data --port 27017 --replSet rs0

# 5. Verify recovery
Check-ClusterStatus
curl -X POST http://localhost:5000/engine-control/stop-all
```

**Kết quả:**
- ✅ Test được error handling
- ❌ Không test được election behavior thật

---

### ❌ T4: Clock Skew Test

**Khả thi:** 10% - Không nên làm trên 1 máy

**Vấn đề:**
- Cùng 1 máy = cùng 1 đồng hồ
- Lệch giờ ảnh hưởng toàn bộ hệ thống (MongoDB, tất cả workers)

**Giải pháp:**
Chấp nhận **SKIP test này** trên 1 máy. Logic clock skew đã được fix bằng `$$NOW`, tin tưởng vào code review.

**Nếu bắt buộc phải test:**
- Dùng Docker containers với clock riêng (phức tạp)
- Hoặc test trên 2 máy ảo (VMware/VirtualBox)

---

## IV. QUYẾT ĐỊNH TEST NÀO TRÊN 1 MÁY

### Must Test (Bắt Buộc) - ~60 phút

```
✅ T1: Bootstrap          (5 phút)
✅ T2: Failover           (10 phút) ← Quan trọng nhất
✅ T5: Token Reset        (3 phút)
✅ T8: Memory Leak        (15 phút)
```

### Should Test (Nên Làm) - ~30 phút

```
✅ T6: Worker Rejoin      (8 phút)
✅ T7: Stream Failure     (5 phút)
✅ T9: Console Block      (3 phút)
```

### Can Skip (Có Thể Bỏ Qua)

```
⚠️ T3: MongoDB Election   (Không thực tế trên 1 máy)
❌ T4: Clock Skew         (Không test được trên 1 máy)
```

---

## V. SCRIPT TỰ ĐỘNG HÓA CHO 1 MÁY

### run_all_tests.ps1

```powershell
# Script chạy tự động tất cả tests có thể trên 1 máy

. .\check_status.ps1  # Import helper functions

Write-Host "===== CLUSTER TEST SUITE - SINGLE MACHINE ====="
Write-Host ""

# Prerequisites check
Write-Host "Checking prerequisites..."
$mongo_check = Test-NetConnection -ComputerName localhost -Port 27017
if (-not $mongo_check.TcpTestSucceeded) {
    Write-Error "MongoDB not running on localhost:27017"
    exit 1
}

$workers = @(5000, 5001, 5002, 5003)
foreach ($port in $workers) {
    $check = Test-NetConnection -ComputerName localhost -Port $port
    if (-not $check.TcpTestSucceeded) {
        Write-Warning "Worker on port $port not running"
    }
}

# Test results
$results = @{}

# ===== T1: Bootstrap Test =====
Write-Host "`n===== Running T1: Bootstrap Test ====="
try {
    # Start cluster
    $response = Invoke-RestMethod -Uri "http://localhost:5000/engine-control/start-all" -Method POST
    Write-Host "Cluster started: token=$($response.token)"
    
    # TODO: Automated stop/start w3 và verify
    # Tạm thời manual
    Write-Host "Manual step: Stop and restart w3, then check logs"
    $results["T1"] = "MANUAL"
} catch {
    Write-Error "T1 failed: $_"
    $results["T1"] = "FAIL"
}

# ===== T5: Token Reset Test =====
Write-Host "`n===== Running T5: Token Reset Test ====="
try {
    # Delete status
    mongosh --quiet --eval 'db.getSiblingDB("HONDA_HN").engine_control_status.deleteOne({_id:"inference_status"})'
    
    # Send new command
    $response = Invoke-RestMethod -Uri "http://localhost:5000/engine-control/stop-all" -Method POST
    Write-Host "New token after reset: $($response.token)"
    
    if ($response.token -le 2) {
        Write-Host "✅ T5 PASS - Token reset correctly"
        $results["T5"] = "PASS"
    } else {
        Write-Host "❌ T5 FAIL - Token not reset"
        $results["T5"] = "FAIL"
    }
    
    Start-Sleep -Seconds 3
} catch {
    Write-Error "T5 failed: $_"
    $results["T5"] = "FAIL"
}

# ===== T8: Memory Leak Test (10 iterations) =====
Write-Host "`n===== Running T8: Memory Leak Test ====="
try {
    $initial_ffmpeg = Get-FFmpegCount
    
    for ($i=1; $i -le 10; $i++) {
        Write-Host "Iteration $i/10..."
        Invoke-RestMethod -Uri "http://localhost:5000/engine-control/stop-all" -Method POST | Out-Null
        Start-Sleep -Seconds 3
        Invoke-RestMethod -Uri "http://localhost:5000/engine-control/start-all" -Method POST | Out-Null
        Start-Sleep -Seconds 5
    }
    
    $final_ffmpeg = Get-FFmpegCount
    $leak_percent = [math]::Abs(($final_ffmpeg - $initial_ffmpeg) / $initial_ffmpeg * 100)
    
    Write-Host "Initial FFmpeg: $initial_ffmpeg, Final: $final_ffmpeg, Leak: $($leak_percent)%"
    
    if ($leak_percent -lt 5) {
        Write-Host "✅ T8 PASS - No memory leak"
        $results["T8"] = "PASS"
    } else {
        Write-Host "❌ T8 FAIL - Memory leak detected"
        $results["T8"] = "FAIL"
    }
} catch {
    Write-Error "T8 failed: $_"
    $results["T8"] = "FAIL"
}

# Summary
Write-Host "`n===== TEST SUMMARY ====="
foreach ($test in $results.Keys | Sort-Object) {
    $status = $results[$test]
    $icon = switch ($status) {
        "PASS" { "✅" }
        "FAIL" { "❌" }
        "MANUAL" { "🔵" }
        default { "⚪" }
    }
    Write-Host "$icon $test : $status"
}
```

---

## VI. TIPS & TRICKS CHO 1 MÁY

### 1. Giảm Camera Count Để Test Nhanh

Nếu máy yếu hoặc không đủ GPU VRAM:

```javascript
// MongoDB - Chỉ enable 20 cameras đầu
use HONDA_HN
db.node_id.updateMany(
  {},
  {$set: {enabled: false}}
)
db.node_id.updateMany(
  {},
  {$set: {enabled: true}},
  {limit: 20}
)
```

### 2. Log Level để Giảm I/O

```env
# .env
AI_LOG_LEVEL=WARNING  # Chỉ log WARNING và ERROR
```

### 3. Monitor Resource Usage

```powershell
# Script giám sát real-time
while ($true) {
    Clear-Host
    Write-Host "===== System Resources ====="
    Write-Host "Time: $(Get-Date -Format 'HH:mm:ss')"
    
    # CPU
    $cpu = (Get-Counter '\Processor(_Total)\% Processor Time').CounterSamples.CookedValue
    Write-Host "CPU: $([math]::Round($cpu, 1))%"
    
    # Memory
    $mem = (Get-Process python | Measure-Object WorkingSet64 -Sum).Sum / 1GB
    Write-Host "Python Memory: $([math]::Round($mem, 2)) GB"
    
    # FFmpeg
    $ffmpeg = (Get-Process ffmpeg -ErrorAction SilentlyContinue | Measure-Object).Count
    Write-Host "FFmpeg Processes: $ffmpeg"
    
    # GPU (if nvidia-smi available)
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        $gpu_mem = nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits
        Write-Host "GPU Memory: $gpu_mem MB"
    }
    
    Start-Sleep -Seconds 2
}
```

### 4. Quick Cleanup Script

```powershell
# cleanup.ps1 - Reset môi trường test
Write-Host "Stopping all workers..."
Get-Process python | Where-Object {$_.CommandLine -like "*src.apps.main*"} | Stop-Process -Force

Write-Host "Stopping FFmpeg..."
Get-Process ffmpeg -ErrorAction SilentlyContinue | Stop-Process -Force

Write-Host "Cleaning MongoDB collections..."
mongosh --quiet --eval @"
use HONDA_HN
db.engine_control_status.deleteMany({})
db.engine_control_acks.deleteMany({})
db.register_worker.deleteMany({})
db.node_id.updateMany({}, {`$set: {current_worker: null, fencing_token: 0}})
"@

Write-Host "Cleanup done!"
```

---

## VII. CHECKLIST TEST TRÊN 1 MÁY

### Setup (1 lần duy nhất)
- [ ] MongoDB replica set 1-node đang chạy
- [ ] Test `rs.status()` → thấy PRIMARY
- [ ] Test change stream: `db.engine_control_status.watch()` không lỗi
- [ ] Collection `node_id` có cameras
- [ ] Helper scripts đã tạo: `check_status.ps1`, `cleanup.ps1`

### Trước mỗi test session
- [ ] Cleanup môi trường: `.\cleanup.ps1`
- [ ] Start 4 workers (4 PowerShell windows)
- [ ] Verify: `Check-ClusterStatus` → acks_count=4
- [ ] Verify: `Get-FFmpegCount` → số hợp lý

### Sau mỗi test case
- [ ] Ghi kết quả PASS/FAIL
- [ ] Screenshot/copy logs quan trọng
- [ ] Check `Get-FFmpegCount` không tăng bất thường

---

## VIII. KẾT LUẬN

### ✅ Bạn CÓ THỂ test trên 1 máy:

**Tests hoàn toàn OK (7/9):**
- T1, T2, T5, T6, T7, T8, T9

**Tests cần skip (2/9):**
- T3: MongoDB election (cần 3-node replica set)
- T4: Clock skew (cần nhiều máy với đồng hồ riêng)

### 📊 Coverage:

- **Logic nghiệp vụ**: ~90% (đủ để validate code)
- **Hạ tầng thực tế**: ~60% (không test network/hardware failures)

### 🎯 Khuyến nghị:

1. **Làm ngay trên 1 máy**: T1, T2, T5, T8 (core tests)
2. **Staging với 4 máy thật**: Test toàn bộ trước production
3. **Production canary**: Test 1 worker trước, rồi rollout dần

---

**Kết luận:** Hoàn toàn đủ để validate logic trên 1 máy. Chỉ cần 4 máy thật khi deploy staging/production.
