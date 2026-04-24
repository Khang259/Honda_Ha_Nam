# Camera Control API - Test Guide

## Tổng quan

Hệ thống camera control API đã được implement thành công với kiến trúc:
- **Worker** expose internal HTTP endpoint (port 5002) để điều khiển camera_manager
- **API Server** làm proxy giữa UI và Worker, cung cấp SSE streaming
- **UI** sử dụng CameraAPIClient để gọi API thay vì truy cập trực tiếp camera_manager

## Thứ tự khởi động services

### 1. Start API Server
```bash
cd d:/Honda/ai_project/ai-nvdec-snapshot-2task-processor-docker
python -m api.main_api
```

Kiểm tra API server đã chạy:
```bash
curl http://192.168.1.30:5001/health
```

### 2. Start AI Worker
```bash
cd d:/Honda/ai_project/ai-nvdec-snapshot-2task-processor-docker
python -m worker.main_worker
```

Worker sẽ tự động:
- Khởi động camera_manager
- Start camera service HTTP server trên port 5002
- Tất cả camera mặc định là **DISABLED** (enabled=False)

Kiểm tra worker camera service:
```bash
curl http://localhost:5002/internal/health
```

### 3. Start UI
```bash
cd d:/Honda/ai_project/ai-nvdec-snapshot-2task-processor-docker
python -m ui.main_ui
```

UI sẽ:
- Connect đến API server (5001)
- Hiển thị các nút "Start All", "Stop All", "AE5 On/Off", "AE6 On/Off"
- Các nút này giờ đã hoạt động và gọi API

## Test từng bước

### Test 1: Kiểm tra UI hiển thị nút điều khiển

**Kỳ vọng:**
- UI hiển thị các nút: "Start All", "Stop All", "AE5 On", "AE5 Off", "AE6 On", "AE6 Off"
- Các nút AE/start-stop bây giờ đã xuất hiện (trước đây không có vì thiếu camera_manager)

### Test 2: Bật tất cả cameras

**Action:** Click nút "Start All" trên UI

**Kiểm tra:**
```bash
# Check worker camera service status
curl http://localhost:5002/internal/cameras/status
```

**Kỳ vọng:**
```json
{
  "success": true,
  "status": {
    "total": 30,
    "alive": 30,
    "enabled": 30
  }
}
```

**Log kiểm tra:**
- `logs/camera_service/log_*.log`: "All cameras started via API"
- `logs/camera_manager/log_*.log`: "All cameras enabled"
- `logs/camera_api_client/log_*.log`: "All cameras started successfully"

### Test 3: Kiểm tra camera bắt đầu gửi detection

**Sau khi bật cameras**, kiểm tra:

```bash
# Xem state points có được update không
curl http://192.168.1.30:5001/state/points | python -m json.tool
```

**Kỳ vọng:**
- Các node_id bắt đầu có state thay đổi (từ False → True khi có object)
- Time được update
- State không còn trống/mặc định nữa

### Test 4: Bật zone AE5

**Action:** Click "AE5 On" trên UI

**Kiểm tra:**
```bash
curl http://localhost:5002/internal/cameras/status
```

**Kỳ vọng:**
- Chỉ cameras có zone="AE5" được enabled
- Các zone khác vẫn disabled

### Test 5: Toggle node flag

**Action:** Click vào button "F" (flag) của một node bất kỳ trong UI

**Kiểm tra:**
```bash
curl http://192.168.1.30:5001/state/points | grep "flag"
```

**Kỳ vọng:**
- Flag của node đó đổi từ False → True hoặc ngược lại
- UI update màu button flag ngay lập tức

**Log kiểm tra:**
- `logs/cameras_routes/log_*.log`: "Toggled flag for start_xxxxx: False -> True"

### Test 6: SSE streaming (Optional - for advanced testing)

**Test bằng curl:**
```bash
curl -N http://192.168.1.30:5001/cameras/AE5/stream
```

**Kỳ vọng:**
- Stream trả về JSON events liên tục:
```
data: {"zone": "AE5", "nodes": {"start_10000060": {"state": false, "flag": false}, ...}, "timestamp": 1234567890.123}

data: {"zone": "AE5", "nodes": {"start_10000060": {"state": true, "flag": false}, ...}, "timestamp": 1234567895.456}
```

- Events được gửi khi có thay đổi state/flag
- Heartbeat mỗi 5 giây nếu không có thay đổi

### Test 7: State đổi màu trên UI

**Điều kiện:**
- Cameras đã được bật
- Worker đang gửi detection về API
- StateManager đang nhận và cập nhật state

**Action:** 
1. Đặt object (xe) vào vị trí start_point
2. Quan sát UI

**Kỳ vọng:**
- Cột "St" (state) của node đó đổi từ "F" (đỏ) → "T" (xanh)
- Cột "Time" bắt đầu đếm từ 0s
- Sau 30s, node xuất hiện trong ready_start_list

## Troubleshooting

### Issue: Nút AE/start-stop không hiện

**Nguyên nhân:** UI không nhận được camera_api_client

**Kiểm tra:**
- Log `logs/ui_main/log_*.log` có dòng "CameraAPIClient initialized"
- Log `logs/camera_api_client/log_*.log` tồn tại và có content

### Issue: Bấm nút không có phản ứng

**Nguyên nhân:** Worker camera service chưa chạy hoặc API không kết nối được

**Kiểm tra:**
```bash
curl http://localhost:5002/internal/health
```

Nếu connection refused:
- Worker chưa start xong
- Port 5002 bị conflict
- Check log `logs/worker_main/log_*.log`

### Issue: State không đổi màu

**Nguyên nhân:** Cameras chưa được bật

**Giải pháp:**
1. Click "Start All" trên UI
2. Hoặc call API:
```bash
curl -X POST http://192.168.1.30:5001/cameras/start-all
```

### Issue: SSE không stream

**Nguyên nhân:** 
- StateManager chưa có data
- Zone name không đúng

**Kiểm tra:**
```bash
# Fallback HTTP endpoint
curl http://192.168.1.30:5001/cameras/AE5/status
```

## API Endpoints Summary

### Camera Control
- `POST /cameras/start-all` - Bật tất cả cameras
- `POST /cameras/stop-all` - Tắt tất cả cameras
- `POST /cameras/{zone}/start-all` - Bật cameras trong zone
- `POST /cameras/{zone}/stop-all` - Tắt cameras trong zone
- `POST /cameras/flag/{node_id}` - Toggle flag của node

### State Monitoring
- `GET /cameras/{zone}/stream` - SSE stream state/flag theo zone
- `GET /cameras/{zone}/status` - HTTP snapshot state của zone
- `GET /cameras/{zone}/flag` - Chỉ lấy flags của zone

### Internal (Worker only)
- `POST http://localhost:5002/internal/cameras/start-all`
- `POST http://localhost:5002/internal/cameras/stop-all`
- `POST http://localhost:5002/internal/cameras/zone`
- `GET http://localhost:5002/internal/cameras/status`
- `GET http://localhost:5002/internal/health`

## Kết luận

Sau khi implement xong:
1. ✅ UI có đầy đủ nút điều khiển camera
2. ✅ Nút Start All/Stop All hoạt động
3. ✅ Nút AE5/AE6 On-Off hoạt động
4. ✅ Toggle flag hoạt động qua API
5. ✅ Camera được bật → detection được gửi → state đổi màu trên UI
6. ✅ SSE streaming để realtime update (optional, UI đang dùng polling)

Vấn đề ban đầu "node_id không nhận state và các nút không hiển thị" đã được giải quyết hoàn toàn.
