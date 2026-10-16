# Kịch Bản Test Hệ Thống Cluster Control

## Giải Thích Thuật Ngữ

- **Cluster Control**: Hệ thống điều khiển đồng thời tất cả các worker (máy trạm) trong cụm
- **Worker**: Một máy trạm xử lý inference (w1, w2, w3, w4)
- **Token**: Số phiên bản lệnh, tăng dần mỗi khi có lệnh mới
- **Ack (Acknowledgment)**: Xác nhận worker đã thực thi lệnh thành công
- **Change Stream**: Cơ chế MongoDB đẩy thông báo real-time khi dữ liệu thay đổi
- **Poll**: Cơ chế kiểm tra định kỳ trạng thái trong MongoDB (fallback khi change stream lỗi)
- **Bootstrap**: Quá trình worker khởi động và đồng bộ trạng thái từ MongoDB
- **Fencing Token**: Token sở hữu camera, tăng khi đổi chủ để chặn worker cũ
- **Failover**: Chuyển camera từ worker chết sang worker còn sống
- **Hot-apply**: Thêm/bớt camera mà không restart process

---

## Tiến độ test (lab 1 máy — cập nhật 2026-10-16)

| Mã | Tên | Trạng thái | Ghi chú |
|----|-----|------------|---------|
| **T1** | Bootstrap + zone lock | 🔄 **CẦN LÀM LẠI** | Bước 4–7 (bootstrap) đã chạy được; **Bước 3 + 8** chờ **cluster-wide zone**. Sau khi sửa zone → chạy lại full T1. |
| **T2** | Failover | ✅ **PASS** | DB moves + `Hot-added` + ffmpeg OK (lab ~20 cam) |
| **T3** | Mongo election | ⏸️ **HOÃN** | Làm trên **máy vật lý / cluster thật** (lab 1 máy election quá nhanh, khó quan sát) |
| **T4** | Clock skew | ⏸️ **HOÃN** | Cần **nhiều máy** lệch giờ; không test trên 1 máy |
| **T5** | Token reset | ✅ **PASS** | |
| **T6** | Worker rejoin | ✅ **PASS** | Minimize-move / 5-5-5-5; log `Hot-added`/`Hot-removed` |
| **T7** | Change stream / poll | ✅ **PASS** | |
| **T8** | Memory leak STOP/RUN | ✅ **PASS** | RAM ổn; STOP còn 1 ffmpeg = MediaMTX mock; không leak tích lũy |
| **T9** | Console Quick Edit | ⬜ **CHƯA LÀM** | |

**Blocker T1 bước 3:** Zone stop hiện chỉ **local** → cần implement **cluster-wide zone control** rồi test lại T1 (bước 3 + 8 + toàn bài).

---

## I. YÊU CẦU TRƯỚC KHI TEST

### 1.1 Yêu Cầu Hệ Thống

**MongoDB:**
- [x] MongoDB đang chạy ở chế độ **replica set** (bắt buộc cho change stream)
- [x] Kiểm tra replica set status: `rs.status()`
- [x] MongoDB version ≥ 4.2 (để hỗ trợ `$$NOW` trong aggregation)

**Workers:**
- [x] 4 workers (w1, w2, w3, w4) được cấu hình đúng
- [x] Mỗi worker có:
  - `WORKER_ID`: w1, w2, w3, w4
  - `MONGODB_URL`: trỏ đến replica set
  - `AI_SERVER_PORT`: 5000, 5001, 5002, 5003 (hoặc ports khác)
- [ ] Camera config đã được nạp vào MongoDB collection `node_id`
- [ ] TensorRT models đã được deploy

**Network:**
- [ ] Các máy có thể kết nối với MongoDB replica set
- [ ] Đồng bộ giờ giữa các máy (chênh lệch < 10s)
- [ ] Kiểm tra: `w32tm /query /status` (Windows)

### 1.2 Chuẩn Bị MongoDB

```javascript
// Kết nối MongoDB shell
use HONDA_HN

// Kiểm tra collections tồn tại
db.engine_control_status.find()
db.engine_control_acks.find()
db.node_id.count()  // Phải có camera configs
db.register_worker.find()

// Kiểm tra indexes
db.engine_control_acks.getIndexes()
// Phải có unique index: {worker_id: 1, token: 1}

// Xóa dữ liệu cũ (optional, chỉ khi cần reset)
db.engine_control_status.deleteMany({})
db.engine_control_acks.deleteMany({})
```

### 1.3 Khởi Động Workers

**Terminal 1 (Worker w1):**
```powershell
cd d:/Prj/Honda_Ha_Nam
$env:WORKER_ID="w1"
$env:AI_SERVER_PORT="5000"
python -m src.apps.main
```

**Terminal 2 (Worker w2):**
```powershell
cd d:/Prj/Honda_Ha_Nam
$env:WORKER_ID="w2"
$env:AI_SERVER_PORT="5001"
python -m src.apps.main
```

**Terminal 3 (Worker w3):**
```powershell
cd d:/Prj/Honda_Ha_Nam
$env:WORKER_ID="w3"
$env:AI_SERVER_PORT="5002"
python -m src.apps.main
```

**Terminal 4 (Worker w4):**
```powershell
cd d:/Prj/Honda_Ha_Nam
$env:WORKER_ID="w4"
$env:AI_SERVER_PORT="5003"
python -m src.apps.main
```

### 1.4 Chuẩn Bị Monitoring

**Terminal 5 (Logs Realtime):**
```powershell
# Tail logs của cluster control listener
Get-Content -Path "logs/w1/cluster_control_listener/log_*.log" -Wait -Tail 50
```

**Terminal 6 (MongoDB Watch):**
```javascript
// MongoDB shell - watch changes
use HONDA_HN
db.engine_control_acks.watch()
```

**Terminal 7 (Health Check Script):**
```powershell
# Script kiểm tra nhanh
function Check-ClusterStatus {
    $status = Invoke-RestMethod -Uri "http://localhost:5000/engine-control/cluster-status"
    Write-Host "State: $($status.status.desired_state) | Token: $($status.status.token) | Acks: $($status.acks_count)/4"
    return $status
}
```

---

## II. KỊCH BẢN TEST CHI TIẾT

### T1: Bootstrap Test - Worker Restart Tự Động Đồng Bộ

**Trạng thái (2026-10-16):** 🔄 **CẦN LÀM LẠI** — bootstrap (bước 4–7) đã verify trên lab; bước 3/8 zone **chưa đủ** (thiếu cluster-wide). Sau khi có cluster-wide zone → chạy lại full T1.

**Mục đích**: Xác minh worker mới khởi động/restart sẽ tự động áp dụng trạng thái hiện tại của cluster.

**Liên quan lỗi**: #1 (pause/resume loops), #2 (state cũ), #3 (zone lock)

**Điều kiện ban đầu:**
- 4 workers đang chạy ở trạng thái STOP

#### Bước thực hiện:

**Bước 1: Start cluster**
```powershell
curl -X POST http://localhost:5000/engine-control/start-all
```

**Kết quả mong đợi:**
```json
{
  "accepted": true,
  "token": 1001,  // hoặc số tiếp theo
  "desired_state": "RUN",
  "command": "start-all",
  "updated_by": "w1"
}
```

**Bước 2: Verify tất cả workers đã apply**
```powershell
Check-ClusterStatus
```

**Kết quả mong đợi:**
- `desired_state`: "RUN"
- `acks_count`: 4
- Response time: < 100ms
- Trong log 4 workers thấy:
  ```
  [INFO] Applying RUN command (token=1001)
  [INFO] RUN command applied successfully (token=1001)
  ```

**Bước 3: Khóa zone — ❌ CẦN SỬA (cluster-wide) trước khi chốt T1**

> 🔴 **BLOCKER — chưa PASS bước này**  
> Zone stop hiện chỉ **local** (worker nhận HTTP). Cần **cluster-wide zone control** (Mongo + listener, giống `/start-all`) để:  
> request 1 máy → tắt đúng zone trên **mọi worker** đang giữ camera zone đó.  
>  
> **Trạng thái lab:** phần còn lại T1 (bootstrap) đã chạy; **vẫn phải làm lại T1** sau khi có cluster-wide zone.  
> **Workaround tạm (không đủ chốt T1):** test local zone trên 1 worker — chỉ để debug, không ghi PASS bước 3/8.

```powershell
# SAU KHI có cluster-wide zone — ví dụ (API có thể đổi theo implementation):
# Invoke-RestMethod -Method POST -Uri "http://localhost:5000/engine-control/Sub6/stop-all"
# Verify trên w1..w4: camera zone Sub6 đều enabled=False (không chỉ máy nhận request)
```

**Kết quả mong đợi (sau khi sửa cluster-wide):**
- Zone bị khóa trên **mọi worker** có camera thuộc zone
- `disabled_nodes` / pairing block nhất quán cluster
- Cameras thuộc zone: `enabled=False` trên đúng các worker sở hữu

**Bước 4: Stop worker w3** ✅ (đã verify trên lab — làm lại khi chạy full T1)
```powershell
# Trong terminal w3: Ctrl+C
# Hoặc: Get-Process -Name python | Where-Object {$_.StartInfo.EnvironmentVariables["WORKER_ID"] -eq "w3"} | Stop-Process
```

**Bước 5: Đợi 5 giây**

**Bước 6: Start lại worker w3**
```powershell
cd d:/Prj/Honda_Ha_Nam
$env:WORKER_ID="w3"
$env:AI_SERVER_PORT="5002"
python -m main
```

**Bước 7: Kiểm tra log w3 trong 10 giây đầu**

**Kết quả mong đợi (Critical):**
```
[INFO] Bootstrap: current cluster state=RUN, token=1001, last_applied=-1
[INFO] Applying via bootstrap: state=RUN, token=1001
[INFO] Applying RUN command (token=1001)
[INFO] RUN command applied successfully (token=1001)
```

**Verify database:**
```javascript
db.engine_control_acks.find({worker_id: "w3", token: 1001})
// Phải có 1 document với applied_state: "RUN"
```

**Verify cameras:**
```powershell
curl http://localhost:5002/engine-control/cameras-enable-state
# Cameras của w3 phải enabled: true
```

**Bước 8: Test zone lock không bị xóa — ❌ phụ thuộc bước 3 (cluster-wide)**

```powershell
# Sau khi zone đã khóa cluster-wide:
Invoke-RestMethod -Method POST -Uri "http://localhost:5000/engine-control/stop-all"
Start-Sleep -Seconds 2
Invoke-RestMethod -Method POST -Uri "http://localhost:5000/engine-control/start-all"
Start-Sleep -Seconds 2

# Verify trên nhiều worker (không chỉ :5000)
# Zone vẫn disabled trên mọi máy có camera zone đó
```

**Kết quả mong đợi (sau cluster-wide):**
- Zone vẫn khóa sau STOP/RUN cluster (state trong Mongo, không mất)
- Cluster RUN không clear zone lock
- Mở lại chỉ khi zone start-all (cluster-wide)

#### Tiêu chí PASS (full T1 — chưa đạt cho đến khi làm lại):
- ✅ Bootstrap w3 + ack (đã thấy trên lab) — **phải verify lại** khi chạy lại T1
- ⬜ Bước 3: zone khóa **cluster-wide**
- ⬜ Bước 8: zone lock sống sót sau STOP/RUN cluster
- ⬜ Không AttributeError khi STOP↔RUN

#### Tiêu chí FAIL:
- ❌ Worker w3 không apply RUN (log không thấy "Applying RUN")
- ❌ Cameras không bật
- ❌ Zone lock bị xóa sau RUN cluster / chỉ khóa được 1 máy

#### Known Issues / TODO trước khi chốt T1:
- 🔴 **Zone control chỉ local** → cần **cluster-wide zone** rồi làm lại T1
- ⚠️ Case-sensitive zone (`Sub6` ≠ `SUB6`) → sửa so khớp trong `camera_manager.py` khi làm zone

---

### T2: Failover Test - Camera Mồ Côi Được Chia Lại

**Trạng thái (2026-10-16):** ✅ **PASS** (lab 1 máy, ~20 cam)

**Mục đích**: Xác minh khi 1 worker chết, camera của nó được worker khác nhận và decode ngay (hot-apply).

**Liên quan lỗi**: #4 (hot-apply), #5 (minimize move), #7 (Mongo error), #8 (debounce), #15 (fencing)

**Điều kiện ban đầu:**
- 4 workers đang RUN
- ~78 cameras được chia đều (mỗi worker ~19-20 cameras)

#### Bước thực hiện:

**Bước 1: Snapshot trạng thái ban đầu**
```javascript
// MongoDB shell
db.node_id.aggregate([
  {$group: {_id: "$current_worker", count: {$sum: 1}}},
  {$sort: {_id: 1}}
])

// Lưu kết quả:
// w1: 20 cameras
// w2: 19 cameras
// w3: 19 cameras
// w4: 20 cameras

// Lưu danh sách camera của w1
var w1_cameras = db.node_id.find({current_worker: "w1"}).toArray()
print("w1 cameras:", w1_cameras.map(c => c.cameraId).join(", "))
```

**Bước 2: Kill worker w1**
```powershell
# Stop process w1
# Ctrl+C trong terminal w1
```

**Bước 3: Đợi debounce + heartbeat timeout**
```powershell
Start-Sleep -Seconds 20
# WorkerManager debounce: 2 lần miss × 10s interval = ~20s
```

**Bước 4: Kiểm tra rebalance trong MongoDB**
```javascript
db.node_id.aggregate([
  {$group: {_id: "$current_worker", count: {$sum: 1}}}
])

// Kết quả mong đợi:
// w2: 26-27 cameras (+7-8)
// w3: 26-27 cameras (+7-8)
// w4: 25-26 cameras (+5-6)
// Total = 78 (không mất camera)
```

**Bước 5: Đếm số camera đổi chủ**
```javascript
// Tính số camera w2/w3/w4 đã nhận từ w1
var moves_w2 = db.node_id.count({current_worker: "w2", _id: {$in: w1_cameras.map(c => c._id)}})
var moves_w3 = db.node_id.count({current_worker: "w3", _id: {$in: w1_cameras.map(c => c._id)}})
var moves_w4 = db.node_id.count({current_worker: "w4", _id: {$in: w1_cameras.map(c => c._id)}})

print("Moved to w2:", moves_w2)
print("Moved to w3:", moves_w3)
print("Moved to w4:", moves_w4)
print("Total moves:", moves_w2 + moves_w3 + moves_w4)

// Mong đợi: Total moves ≈ 20 (chỉ chia camera của w1)
// Không đạt nếu: > 40 (thuật toán khối cũ)
```

**Bước 6: Verify hot-apply - cameras thật sự decode**
```powershell
# Kiểm tra log w2
Select-String -Path "logs/w2/camera_manager/log_*.log" -Pattern "add_camera|Starting camera thread"

# Kiểm tra ffmpeg processes
Get-Process -Name ffmpeg | Measure-Object
# Count phải tăng (w2/w3/w4 decode thêm camera mới)

# Kiểm tra API w2
curl http://localhost:5001/engine-control/cameras-enable-state
# Số camera enabled phải = số camera assigned trong DB
```

**Kết quả mong đợi (Critical):**
- Log w2/w3/w4 có:
  ```
  [INFO] WorkerManager: claimed 7 cameras from orphaned
  [INFO] CameraManager: add_camera cameraId=cam_001
  [INFO] Starting camera thread for cam_001
  [INFO] FFmpeg decoder started for cam_001
  ```
- Ffmpeg process count tăng tương ứng
- Không cần restart worker để decode camera mới

**Bước 7: Start lại w1**
```powershell
$env:WORKER_ID="w1"
$env:AI_SERVER_PORT="5000"
python -m src.apps.main
```

**Bước 8: Đợi rebalance lần 2**
```powershell
Start-Sleep -Seconds 15
```

**Bước 9: Kiểm tra move tối thiểu khi w1 quay lại**
```javascript
db.node_id.aggregate([
  {$group: {_id: "$current_worker", count: {$sum: 1}}}
])

// Kết quả mong đợi:
// w1: 19-20 cameras (lấy lại từ máy tải cao nhất)
// w2: 19-20 cameras
// w3: 19-20 cameras
// w4: 19-20 cameras
// Tổng move ≈ 19-20 (không xếp lại cả 78)
```

#### Tiêu chí PASS:
- ✅ Camera mồ côi được chia cho w2/w3/w4
- ✅ Total moves ≤ 25 khi w1 chết (không 40+)
- ✅ Workers thật sự decode camera mới (log + ffmpeg count)
- ✅ Khi w1 quay lại, chỉ ~20 camera chuyển (minimize move)
- ✅ Fencing token tăng, worker cũ không claim được start event của camera đã mất

#### Tiêu chí FAIL:
- ❌ MongoDB đổi `current_worker` nhưng không có thread decode mới
- ❌ > 40 cameras đổi chủ khi 1 worker chết
- ❌ Worker cũ vẫn publish ICS cho camera đã mất

---

### T3: MongoDB Primary Election Test - Không Drop Camera

**Trạng thái (2026-10-16):** ⏸️ **HOÃN** — ưu tiên chạy trên **máy vật lý / Mongo phân tán**. Lab 1 máy: `stepDown` quá nhanh, khó quan sát log skip; smoke `null=0` chưa đủ thay T3 chính thức.

**Mục đích**: Xác minh khi MongoDB primary election, hệ thống không coi là "mất worker" và không release camera hàng loạt.

**Liên quan lỗi**: #7 (Mongo error handling)

#### Bước thực hiện:

**Bước 1: Cluster đang RUN ổn định**
```powershell
Check-ClusterStatus
# Verify: desired_state=RUN, acks_count=4
```

**Bước 2: Kiểm tra replica set status**
```javascript
rs.status()
// Note primary member (vd. mongo1:27017)
```

**Bước 3: Trigger primary election**
```javascript
// Trên primary node
rs.stepDown(60)  // Step down trong 60s

// Hoặc kill primary mongod process
// Hoặc ngắt network của primary tạm thời
```

**Bước 4: Quan sát logs workers trong 30 giây**

**Kết quả mong đợi:**
- Log có:
  ```
  [WARNING] MongoDB operation failed: connection error / primary not available
  [WARNING] WorkerRegistry returned unknown state; skipping rebalance
  [INFO] Retrying MongoDB connection...
  ```
- Log không có:
  ```
  [ERROR] No active workers found
  [INFO] Releasing all cameras  // ❌ KHÔNG ĐƯỢC CÓ
  ```

**Bước 5: Đợi election hoàn tất**
```javascript
rs.status()
// Đợi cho đến khi có primary mới
```

**Bước 6: Kiểm tra MongoDB**
```javascript
db.node_id.aggregate([
  {$match: {current_worker: null}},
  {$count: "orphaned_cameras"}
])

// Kết quả mong đợi: orphaned_cameras = 0
// (hoặc chỉ vài cameras nếu có worker thật sự chết trước đó)
```

**Bước 7: Verify cluster vẫn hoạt động**
```powershell
Check-ClusterStatus
curl -X POST http://localhost:5000/engine-control/stop-all
Start-Sleep -Seconds 2
curl -X POST http://localhost:5000/engine-control/start-all
```

**Kết quả mong đợi:**
- Lệnh vẫn được apply sau khi election xong
- Không có camera nào bị mất chủ

#### Tiêu chí PASS:
- ✅ Primary election không gây release camera hàng loạt
- ✅ Log có skip rebalance với lý do "unknown state"
- ✅ Sau election, cluster hoạt động bình thường

#### Tiêu chí FAIL:
- ❌ Nhiều camera `current_worker=null` sau election
- ❌ Workers bị panic/crash khi MongoDB lỗi
- ❌ Không retry kết nối MongoDB

---

### T4: Clock Skew Test - Đồng Hồ Lệch Không Gây Ping-Pong

**Trạng thái (2026-10-16):** ⏸️ **HOÃN** — cần **tối thiểu 2 máy** lệch giờ; không thực hiện trên lab 1 máy.

**Mục đích**: Xác minh hệ thống dùng giờ server (`$$NOW`) để tránh ping-pong camera khi máy lệch giờ.

**Liên quan lỗi**: #6 (clock skew)

#### Bước thực hiện:

**Bước 1: Sync giờ ban đầu**
```powershell
# Trên tất cả 4 máy Windows
w32tm /resync /force
w32tm /query /status

# Verify time difference < 5s
```

**Bước 2: Giả lập lệch giờ +40s trên máy w3**
> ⚠️ **Lưu ý**: Test này có thể ảnh hưởng hệ thống. Làm trên máy test riêng.

```powershell
# Trên máy w3 (Windows)
# Tạm thời tắt time sync
Set-Service -Name w32time -StartupType Disabled
Stop-Service -Name w32time

# Chỉnh giờ +40s (GUI: Control Panel > Date and Time)
# Hoặc dùng PowerShell (cần admin):
$newTime = (Get-Date).AddSeconds(40)
Set-Date $newTime
```

**Bước 3: Khởi động lại worker w3**
```powershell
python -m src.apps.main
```

**Bước 4: Quan sát heartbeat và camera assignment**
```javascript
// MongoDB shell - watch heartbeats
db.register_worker.find().sort({last_heartbeat_utc: -1})

// Watch camera assignments của w3
db.node_id.aggregate([
  {$match: {current_worker: "w3"}},
  {$count: "w3_cameras"}
])
```

**Bước 5: Đợi 5 phút, kiểm tra liên tục**
```powershell
# Script kiểm tra mỗi 10s
for ($i=0; $i -lt 30; $i++) {
    $w3_count = (mongo --quiet --eval "db.node_id.count({current_worker: 'w3'})")
    Write-Host "$(Get-Date -Format 'HH:mm:ss') - w3 cameras: $w3_count"
    Start-Sleep -Seconds 10
}
```

**Kết quả mong đợi:**
- Số camera của w3 ổn định (~19-20)
- Không có ping-pong: camera liên tục chuyển w3 ↔ w2/w4
- Log không có:
  ```
  [WARNING] Worker w3 heartbeat expired (local time)  // ❌ KHÔNG ĐƯỢC CÓ
  ```
- MongoDB heartbeat dùng giờ server:
  ```javascript
  db.register_worker.findOne({worker_id: "w3"})
  // last_heartbeat_utc phải là server time, không phải client time +40s
  ```

**Bước 6: Khôi phục giờ w3**
```powershell
# Sync lại giờ
Set-Service -Name w32time -StartupType Automatic
Start-Service -Name w32time
w32tm /resync /force
```

#### Tiêu chí PASS:
- ✅ Lệch giờ +40s không gây camera ping-pong
- ✅ Heartbeat/cutoff dùng `$$NOW` (server time)
- ✅ Worker w3 không bị coi là dead do lệch giờ local

#### Tiêu chí FAIL:
- ❌ Camera liên tục chuyển giữa w3 và workers khác
- ❌ Heartbeat dùng client time (bị lệch)

---

### T5: Token Reset Test - Lệnh Vẫn Apply Sau Reset DB

**Trạng thái (2026-10-16):** ✅ **PASS**

**Mục đích**: Xác minh hệ thống vẫn hoạt động khi MongoDB bị reset hoặc token về 0.

**Liên quan lỗi**: #10 (token ordering)

#### Bước thực hiện:

**Bước 1: Workers đang RUN với token cao**
```powershell
Check-ClusterStatus
# Giả sử: token=1010
```

**Bước 2: Xóa status document**
```javascript
db.engine_control_status.deleteOne({_id: "inference_status"})

// Verify
db.engine_control_status.count()  // = 0
```

**Bước 3: Gửi lệnh mới (token sẽ reset về 1)**
```powershell
curl -X POST http://localhost:5000/engine-control/stop-all
```

**Kết quả mong đợi:**
```json
{
  "accepted": true,
  "token": 1,  // token mới từ đầu
  "desired_state": "STOP"
}
```

**Bước 4: Kiểm tra logs tất cả workers**

**Kết quả mong đợi:**
```
[WARNING] Token went backwards via change_stream: token=1 < last_applied=1010; will re-apply
[INFO] Applying STOP command (token=1)
[INFO] STOP command applied successfully (token=1)
```

**Bước 5: Verify database**
```javascript
db.engine_control_acks.find({token: 1})
// Phải có 4 acks với token=1

db.engine_control_status.findOne()
// {desired_state: "STOP", token: 1}
```

**Bước 6: Test tiếp lệnh START**
```powershell
curl -X POST http://localhost:5000/engine-control/start-all
```

**Kết quả mong đợi:**
- Token tăng lên 2
- 4 workers apply RUN
- Hệ thống hoạt động bình thường

#### Tiêu chí PASS:
- ✅ Token reset (1010 → 1) vẫn được apply
- ✅ Log WARNING khi token giảm
- ✅ Cluster hoạt động bình thường sau reset

#### Tiêu chí FAIL:
- ❌ Workers bỏ qua lệnh vì token nhỏ hơn
- ❌ Không có log WARNING

---

### T6: Worker Rejoin Test - Move Tối Thiểu

**Trạng thái (2026-10-16):** ✅ **PASS** (lab ~20 cam, phân bố 5/5/5/5 sau w4 rejoin)

**Mục đích**: Xác minh khi worker quay lại, chỉ số camera tối thiểu được chuyển (không rebalance toàn bộ).

**Liên quan lỗi**: #4 (hot-apply), #5 (minimize move)

#### Bước thực hiện:

**Bước 1: 4 workers RUN, snapshot**
```javascript
var before = db.node_id.aggregate([
  {$group: {_id: "$current_worker", count: {$sum: 1}, cameras: {$push: "$cameraId"}}}
]).toArray()

printjson(before)
// w1: 20, w2: 19, w3: 19, w4: 20
```

**Bước 2: Kill w4**
```powershell
# Stop w4 process
```

**Bước 3: Đợi rebalance (20s)**

**Bước 4: Snapshot sau khi w4 chết**
```javascript
var after_w4_down = db.node_id.aggregate([
  {$group: {_id: "$current_worker", count: {$sum: 1}}}
]).toArray()

printjson(after_w4_down)
// w1: 27, w2: 25, w3: 26 (tổng = 78)
```

**Bước 5: Start lại w4**
```powershell
$env:WORKER_ID="w4"
$env:AI_SERVER_PORT="5003"
python -m src.apps.main
```

**Bước 6: Đợi rebalance (20s)**

**Bước 7: Snapshot cuối**
```javascript
var after_w4_back = db.node_id.aggregate([
  {$group: {_id: "$current_worker", count: {$sum: 1}}}
]).toArray()

printjson(after_w4_back)
// Mong đợi: trở về gần ban đầu (w1:20, w2:19, w3:19, w4:20)

// Đếm số camera đổi chủ
var moved_back_count = 0
before[3].cameras.forEach(function(cam) {
  var current = db.node_id.findOne({cameraId: cam})
  if (current.current_worker === "w4") {
    moved_back_count++
  }
})

print("Cameras moved back to w4:", moved_back_count)
// Mong đợi: ~19-20 (không 78)
```

**Bước 8: Verify hot-remove trên w1/w2/w3**
```powershell
# Kiểm tra log
Select-String -Path "logs/w1/camera_manager/log_*.log" -Pattern "remove_camera|Stopping camera thread"

# Kiểm tra ffmpeg count giảm
Get-Process -Name ffmpeg | Measure-Object
# Count phải giảm tương ứng số camera trả lại cho w4
```

#### Tiêu chí PASS:
- ✅ Khi w4 quay lại, chỉ ~19-20 camera chuyển về w4
- ✅ Không rebalance toàn bộ 78 cameras
- ✅ Hot-add/remove hoạt động (log + ffmpeg count)
- ✅ Distribution cuối cùng: mỗi worker 19-20 cameras

#### Tiêu chí FAIL:
- ❌ > 40 cameras đổi chủ khi w4 quay lại
- ❌ Cameras trong DB đổi nhưng không decode/stop thread

---

### T7: Change Stream Failure Test - Poll Fallback

**Trạng thái (2026-10-16):** ✅ **PASS**

**Mục đích**: Xác minh khi change stream lỗi, hệ thống tự động fallback sang polling và vẫn nhận lệnh.

**Liên quan lỗi**: #9 (change stream resilience)

#### Bước thực hiện:

**Bước 1: Cluster đang RUN**

**Bước 2: Giả lập change stream failure**

**Cách 1: Downgrade MongoDB về standalone**
```javascript
// ⚠️ Chỉ làm trên môi trường test
// Stop tất cả mongod
// Start lại 1 mongod standalone (không replica set)
mongod --dbpath /data/db --port 27017
```

**Cách 2: Block network đến MongoDB secondary**
```powershell
# Trên firewall hoặc network adapter của secondary
```

**Bước 3: Restart 1 worker (vd. w2)**
```powershell
# Stop w2
# Start w2 lại
```

**Bước 4: Kiểm tra log w2**

**Kết quả mong đợi:**
```
[WARNING] Change stream unavailable (error: replica set required); falling back to polling
[INFO] Starting reconcile poll loop (interval=5.0s)
```

**Bước 5: Gửi lệnh cluster**
```powershell
curl -X POST http://localhost:5000/engine-control/stop-all
```

**Bước 6: Quan sát log w2**

**Kết quả mong đợi (sau ~5 giây):**
```
[INFO] Poll detected new command: state=STOP, token=1011
[INFO] Applying via poll: state=STOP, token=1011
[INFO] Applying STOP command (token=1011)
[INFO] STOP command applied successfully (token=1011)
```

**Bước 7: Verify latency**
- Latency tăng lên ~5 giây (poll interval)
- Nhưng lệnh vẫn được apply thành công

**Bước 8: Khôi phục change stream**
```powershell
# Restore replica set
# Restart workers
```

**Bước 9: Verify change stream hoạt động lại**
```
[INFO] Starting change stream watch on engine_control_status
```

#### Tiêu chí PASS:
- ✅ Change stream lỗi → tự động fallback polling
- ✅ Lệnh mới vẫn được apply trong ~5s (poll interval)
- ✅ Không crash worker khi stream unavailable
- ✅ Tự động reconnect stream khi có thể

#### Tiêu chí FAIL:
- ❌ Worker chết im lặng khi stream lỗi
- ❌ Lệnh mới không bao giờ được apply
- ❌ Không có log fallback polling

---

### T8: Memory Leak Test - STOP/RUN Lặp Lại

**Trạng thái (2026-10-16):** ✅ **PASS** — RAM ~4.5 GB ổn định; STOP còn FFmpeg=1 do MediaMTX mock; RUN ~16–21 không tăng dần (không leak tích lũy).

**Mục đích**: Xác minh không có leak tài nguyên (ffmpeg sót, RAM Python, VRAM) sau nhiều lần STOP/RUN cluster.

**Liên quan lỗi**: #14 (ffmpeg timeout / cleanup), #21 (batch size)

**Cách đo đúng (quan trọng):**
- Baseline phải lấy khi cluster **RUN ổn định** (ffmpeg ≈ số camera, vd. ~20).
- Mỗi vòng đo **2 mốc**: sau STOP (kỳ vọng ~0) và sau START (kỳ vọng ≈ baseline).
- Đợi đủ lâu sau STOP/START — đo sớm sẽ thấy 1↔21 giả (timing), không phải leak.
- Leak thật = ffmpeg/RAM **tăng dần qua các vòng và không tụt về**.

> PowerShell: dùng `Invoke-RestMethod` (hoặc `curl.exe`), không dùng `curl -X` (alias Invoke-WebRequest).

#### Bước thực hiện:

**Bước 0: Đưa cluster RUN ổn định**
```powershell
cd D:\Prj\Honda_Ha_Nam
Invoke-RestMethod -Method POST -Uri "http://localhost:5000/engine-control/start-all" | Out-Null
Start-Sleep -Seconds 30   # đợi camera/ffmpeg lên đủ
```

**Bước 1: Snapshot baseline (khi đang RUN)**
```powershell
$initial_ffmpeg = @(Get-Process -Name ffmpeg -ErrorAction SilentlyContinue).Count
$initial_mem = (
  Get-Process -Name python -ErrorAction SilentlyContinue |
  Measure-Object -Property WorkingSet64 -Sum
).Sum / 1GB
$initial_gpu = (nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>$null)

Write-Host "Baseline (RUN): FFmpeg=$initial_ffmpeg  Memory=$([math]::Round($initial_mem,2)) GB  GPU_MB=$initial_gpu"
# Kỳ vọng FFmpeg ≈ số camera lab (vd. 20). Nếu = 0 hoặc 1 → chưa sẵn sàng, đừng chạy loop.
if ($initial_ffmpeg -lt 5) {
  Write-Warning "Baseline ffmpeg quá thấp — kiểm tra cluster RUN / RTSP trước khi test T8"
}
```

**Bước 2: Loop STOP/RUN (đo 2 mốc mỗi vòng)**
```powershell
$stopCounts = @()
$runCounts  = @()
$memRuns    = @()

for ($i = 1; $i -le 20; $i++) {
  Write-Host "===== Iteration $i ====="

  # --- STOP ---
  Invoke-RestMethod -Method POST -Uri "http://localhost:5000/engine-control/stop-all" | Out-Null
  Start-Sleep -Seconds 15
  $ffmpeg_stop = @(Get-Process -Name ffmpeg -ErrorAction SilentlyContinue).Count
  $stopCounts += $ffmpeg_stop
  Write-Host "  After STOP : FFmpeg=$ffmpeg_stop  (kỳ vọng ~0)"

  # --- RUN ---
  Invoke-RestMethod -Method POST -Uri "http://localhost:5000/engine-control/start-all" | Out-Null
  Start-Sleep -Seconds 25
  $ffmpeg_run = @(Get-Process -Name ffmpeg -ErrorAction SilentlyContinue).Count
  $mem = (
    Get-Process -Name python -ErrorAction SilentlyContinue |
    Measure-Object -Property WorkingSet64 -Sum
  ).Sum / 1GB
  $runCounts += $ffmpeg_run
  $memRuns   += $mem
  Write-Host "  After RUN  : FFmpeg=$ffmpeg_run  Memory=$([math]::Round($mem,2)) GB  (kỳ vọng ≈ $initial_ffmpeg)"

  # Cảnh báo leak: sau STOP vẫn cao, hoặc sau RUN vượt baseline rõ
  if ($ffmpeg_stop -gt [Math]::Max(2, [int]($initial_ffmpeg * 0.2))) {
    Write-Warning "  STOP cleanup yếu: còn $ffmpeg_stop ffmpeg"
  }
  if ($initial_ffmpeg -gt 0 -and $ffmpeg_run -gt ($initial_ffmpeg * 1.25)) {
    Write-Warning "  RUN vượt baseline: $ffmpeg_run > $($initial_ffmpeg * 1.25)"
  }
  if ($ffmpeg_run -lt [Math]::Max(1, [int]($initial_ffmpeg * 0.5))) {
    Write-Warning "  RUN chưa đủ ffmpeg (timing/RTSP?) — không kết luận leak từ mốc này"
  }
}
```

**Bước 3: Snapshot cuối + tóm tắt**
```powershell
# Đảm bảo đang RUN rồi đo final
Invoke-RestMethod -Method POST -Uri "http://localhost:5000/engine-control/start-all" | Out-Null
Start-Sleep -Seconds 25

$final_ffmpeg = @(Get-Process -Name ffmpeg -ErrorAction SilentlyContinue).Count
$final_mem = (
  Get-Process -Name python -ErrorAction SilentlyContinue |
  Measure-Object -Property WorkingSet64 -Sum
).Sum / 1GB
$final_gpu = (nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>$null)

Write-Host "===== T8 Summary ====="
Write-Host "Baseline FFmpeg=$initial_ffmpeg  Final(RUN)=$final_ffmpeg"
Write-Host "Baseline Memory=$([math]::Round($initial_mem,2)) GB  Final=$([math]::Round($final_mem,2)) GB"
Write-Host "GPU_MB baseline=$initial_gpu  final=$final_gpu"
Write-Host "STOP ffmpeg max=$($stopCounts | Measure-Object -Maximum | Select -Expand Maximum)  (nên thấp)"
Write-Host "RUN  ffmpeg min=$($runCounts | Measure-Object -Minimum | Select -Expand Minimum) max=$($runCounts | Measure-Object -Maximum | Select -Expand Maximum)"
```

**Bước 4: Kiểm tra process sót (optional)**
```powershell
Get-Process -Name ffmpeg -ErrorAction SilentlyContinue |
  Select-Object Id, StartTime |
  Sort-Object StartTime

# Lab cleanup nếu kẹt (không phải cách “ngăn leak” trong app):
# Get-Process ffmpeg -ErrorAction SilentlyContinue | Stop-Process -Force
```

#### Kết quả mong đợi:
- Sau STOP: FFmpeg ≈ 0–2 (không giữ gần bằng số camera)
- Sau RUN: FFmpeg ≈ baseline (±20%)
- Final (RUN) ≈ baseline; Memory tăng &lt; 20%
- GPU MB không tăng đều qua 20 vòng
- Không phải pattern: 20 → 25 → 32 → 40 (tăng mãi)

#### Tiêu chí PASS:
- ✅ Sau STOP, ffmpeg tụt mạnh (không “kẹt” gần baseline)
- ✅ Sau RUN ổn định, ffmpeg ≈ baseline; cuối test không cao hơn baseline &gt; 25%
- ✅ RAM Python tăng &lt; 20%
- ✅ Không có xu hướng ffmpeg tăng dần mỗi vòng

#### Tiêu chí FAIL:
- ❌ Sau STOP vẫn còn gần đủ số ffmpeg của lúc RUN, và tăng dần
- ❌ Sau RUN: 20 → 28 → 35… không bao giờ về gần baseline
- ❌ RAM tăng &gt; 50% hoặc VRAM tăng rõ qua vòng
- ❌ (Riêng) Nhiều vòng RUN chỉ còn 1 ffmpeg khi baseline ~20 → lỗi start/RTSP, ghi chú riêng, không gọi là “PASS leak”

#### Ghi chú diễn giải:
- FFmpeg dao động `1 ↔ 21` khi sleep ngắn = **đo lệch pha**, chưa đủ kết luận leak.
- WARNING chỉ đáng tin khi baseline đúng (RUN đủ cam) và sau STOP/RUN đã settle.

---

### T9: Console Quick Edit Test - Không Treo Heartbeat

**Trạng thái (2026-10-16):** ⬜ **CHƯA THỰC HIỆN**

**Mục đích**: Xác minh console Windows Quick Edit mode không block heartbeat.

**Liên quan lỗi**: #17 (console blocking)

#### Bước thực hiện:

**Bước 1: Enable Quick Edit trên console worker w1**
```
Right-click console title bar → Properties → Options
[✓] Quick Edit Mode
```

**Bước 2: Worker w1 đang RUN**

**Bước 3: Click vào console w1 (vào edit mode)**
```
# Console sẽ hiển thị "Select" ở title bar
# Process bị pause
```

**Bước 4: Đợi 60 giây (không nhấn phím gì)**

**Bước 5: Kiểm tra MongoDB heartbeat**
```javascript
// Trong khi console bị pause
db.register_worker.find({worker_id: "w1"}).sort({last_heartbeat_utc: -1})

// Kiểm tra timestamp có update không
```

**Bước 6: Kiểm tra camera assignment**
```javascript
// Sau 30s (> heartbeat timeout)
db.node_id.aggregate([
  {$group: {_id: "$current_worker", count: {$sum: 1}}}
])

// Kiểm tra w1 có bị coi là dead không
```

**Bước 7: Nhấn Enter để thoát edit mode**

**Bước 8: Verify w1 tiếp tục hoạt động**

#### Kết quả mong đợi (với fix):
- Heartbeat tiếp tục update (log level = WARNING, không spam console)
- Camera không bị chuyển từ w1 sang worker khác
- Log có thể delay nhưng background tasks vẫn chạy

#### Kết quả nếu không fix:
- Console pause → heartbeat dừng
- Sau 30s, w1 bị coi là dead
- Cameras chuyển sang w2/w3/w4

#### Fix recommendation:
- Set `AI_LOG_LEVEL=WARNING` trong production
- Hoặc disable console logging: `--log-config` với file-only handlers
- Hoặc disable Quick Edit trong console properties

#### Tiêu chí PASS:
- ✅ Console pause không ảnh hưởng heartbeat
- ✅ Worker không bị coi là dead khi console edit mode

#### Tiêu chí FAIL:
- ❌ Heartbeat dừng khi console pause
- ❌ Cameras bị chuyển chủ

---

## III. CHECKLIST TỔNG HỢP

### Trước khi bắt đầu test:
- [ ] MongoDB replica set đang chạy
- [ ] 4 workers được cấu hình đúng
- [ ] Đồng bộ giờ < 10s
- [ ] Cameras đã được load vào DB
- [ ] Backup MongoDB collections

### Sau mỗi test case:
- [ ] Ghi lại kết quả PASS/FAIL
- [ ] Screenshot/copy logs quan trọng
- [ ] Reset môi trường về trạng thái clean (nếu cần)
- [ ] Verify MongoDB consistency

### Khi hoàn thành (cập nhật 2026-10-16):
- [ ] T1 PASS - Bootstrap + zone — 🔄 **cần làm lại** (bước 3 chờ cluster-wide zone; bootstrap lab đã smoke)
- [x] T2 PASS - Failover
- [ ] T3 PASS - MongoDB election — ⏸️ **hoãn máy vật lý**
- [ ] T4 PASS - Clock skew — ⏸️ **hoãn máy vật lý**
- [x] T5 PASS - Token reset
- [x] T6 PASS - Worker rejoin
- [x] T7 PASS - Change stream fallback
- [x] T8 PASS - Memory leak (lab + MediaMTX)
- [ ] T9 PASS - Console pause — ⬜ **chưa làm**

---

## IV. TROUBLESHOOTING

### Issue: Worker không apply lệnh

**Kiểm tra:**
```powershell
# Log có bootstrap message?
Select-String -Path "logs/w*/cluster_control_listener/log_*.log" -Pattern "Bootstrap"

# Log có change detected?
Select-String -Path "logs/w*/cluster_control_listener/log_*.log" -Pattern "Change detected|Poll detected"

# MongoDB document có tồn tại?
```

```javascript
db.engine_control_status.findOne()
```

### Issue: Acks count < 4

**Kiểm tra:**
```powershell
# Tất cả workers có chạy?
Get-Process -Name python | Where-Object {$_.StartInfo.EnvironmentVariables["WORKER_ID"] -ne $null}

# Workers có lỗi?
Select-String -Path "logs/w*/cluster_control_listener/log_*.log" -Pattern "ERROR"

# MongoDB connection OK?
```

### Issue: Camera không decode sau failover

**Kiểm tra:**
```powershell
# Hot-apply có được gọi?
Select-String -Path "logs/w*/camera_manager/log_*.log" -Pattern "add_camera"

# FFmpeg có start?
Select-String -Path "logs/w*/camera_processor/log_*.log" -Pattern "FFmpeg decoder started"

# Thread count có tăng?
Get-Process -Name python | Select-Object -Property Threads
```

### Issue: Token không tăng

**Kiểm tra:**
```javascript
// Route có gọi update_desired_state?
db.engine_control_status.findOne()

// MongoDB có lỗi $inc?
```

```powershell
Select-String -Path "logs/w*/mongo_cluster_control_client/log_*.log" -Pattern "ERROR"
```

---

## V. KẾT QUẢ MONG ĐỢI TỔNG QUAN

### Hệ thống cluster control thành công khi:

1. **Reliability**: Lệnh luôn được apply cho 4/4 workers trong 2-5 giây
2. **Resilience**: Worker restart tự động đồng bộ trạng thái
3. **Failover**: Camera mồ côi được decode ngay không cần restart
4. **Consistency**: MongoDB lỗi không gây drop camera
5. **Ordering**: Token đảm bảo lệnh mới nhất thắng
6. **Efficiency**: Rebalance minimize số camera di chuyển
7. **Stability**: Không leak memory/processes sau STOP/RUN lặp
8. **Monitoring**: Logs rõ ràng, cluster-status API chính xác

### Các chỉ số quan trọng:

| Metric | Target | Critical |
|--------|--------|----------|
| Command latency | < 2s (change stream) | < 5s (polling) |
| Acks count | 4/4 | ≥ 3/4 acceptable |
| Failover camera moves | ≤ 25 (1 worker down) | < 40 |
| Worker rejoin moves | ≤ 25 | < 40 |
| FFmpeg leak rate | 0% | < 5% |
| Memory leak rate | < 10% | < 20% |
| MongoDB recovery time | < 10s | < 30s |

---

**Phiên bản tài liệu**: 1.1  
**Ngày tạo**: 15/10/2026  
**Người tạo**: AI Assistant based on codebase analysis  
**Cập nhật**: 2026-10-16 — tiến độ lab: T2/T5/T6/T7/T8 PASS; T3/T4 hoãn máy vật lý; T9 chưa; T1 cần làm lại sau cluster-wide zone
