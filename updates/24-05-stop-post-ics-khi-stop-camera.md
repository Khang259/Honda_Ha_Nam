# 24-05 — Stop POST ICS khi stop camera

## Tóm tắt thay đổi

Dừng gửi request POST tới ICS khi người dùng stop camera qua API.

| API | Hành vi pairing |
|-----|-----------------|
| `POST /stop-all` | `orchestrator.pause()` — dừng toàn bộ pairing |
| `POST /{zone}/stop-all` | `disable_nodes(zone_nodes)` + `disable_areas({zone})` |
| `POST /flag-camera-id` | `disable_nodes(camera_nodes)` hoặc `enable_nodes` |
| `POST /start-all` | `orchestrator.resume()` — clear disabled nodes/areas |
| `POST /{zone}/start-all` | `enable_nodes` + `enable_areas` |

**Files:** `orchestrator.py`, `dispatcher.py`, `distributed_dispatcher.py`, `cameras.py`, `api_http/state.py`, `runtime_service.py`

---

## Quyết định ngoài spec

- **`pause()` vs selective disable:** Stop-all dùng pause; stop zone/camera dùng disable từng phần, loop vẫn chạy nếu còn zone khác bật.
- **Publisher không bị pause khi stop zone:** Chỉ dispatcher block POST; publisher vẫn publish start lên Mongo nếu `_paused=False`.
- **`resume()` clear toàn bộ disabled state:** Gọi `/start-all` xóa hết `_disabled_nodes` và `_disabled_areas`.
- **`flag-camera-id` chỉ disable nodes:** Không disable cả area.

## Thay đổi so với yêu cầu

| Yêu cầu | Thực tế |
|---------|---------|
| Stop zone → dừng pairing zone | disable nodes + disable area (bổ sung area ở phase sau) |
| stop-all → reset Mongo docs | **Không** — chỉ pause; reset là API admin riêng |
| Pause dispatcher | Đúng — `_is_running()` = `_running and not _paused` |

## Trade-off

| Ưu | Nhược |
|----|-------|
| Stop granular theo zone/camera | Publisher vẫn ghi Mongo khi zone stop |
| Pause toàn hệ khi stop-all | Resume clear hết selective disable |
| Không cần sửa ICS client | Last frame + ready list vẫn có thể tạo candidate trước khi block |

## Review / workflow / dataflow

```
POST /stop-all → orchestrator.pause() → publisher + dispatcher dừng

POST /AE5/stop-all
  → disable_nodes(zone_nodes)
  → disable_areas({"AE5"})
  → set_zone_enabled(False)
  → nếu enabled_count==0 → pause()

Dispatcher mỗi vòng:
  → _should_post_pair / _should_post_empty
  → nếu blocked → skip POST ICS
```

**Checklist:** Mọi path POST ICS trong `dispatcher.py` và `distributed_dispatcher.py` đều qua should_post check.

**Log:** `logs/start_event_pairing/log`, `logs/engine_control_routes/log`
