# Checklist sửa lỗi Cluster Control / Load Balancing

Nguồn: `docs/cluster_control_danh_sach_loi.xlsx` (26 lỗi, nhánh `update_load_balancing`).

Đối chiếu code: **14/10/2026** — cả 26 lỗi vẫn còn trong codebase.

Cách dùng: đánh `[x]` khi xong từng mục. Cột **Test** map với sheet `Kiểm tra sau sửa`.

---

## Tiến độ tổng

| Phase | Phạm vi | Ước lượng | Trạng thái |
|-------|---------|-----------|------------|
| Phase 1 | Cluster control ổn định (STOP/RUN) | ~10 ngày | ☐ Chưa bắt đầu |
| Phase 2 | Failover camera động | ~15 ngày | ☐ Chưa bắt đầu |
| Phase 3 | Vận hành / harden | ~5 ngày | ☐ Chưa bắt đầu |

**Prerequisite trước khi sửa**

- [ ] Backup Mongo: `register_worker`, `node_id`, `engine_control_status`, `engine_control_acks`, `start_events_test`
- [ ] Ghi lại `db.version()` (cần ≥ 4.2 nếu làm lỗi #6 bằng `$$NOW`)
- [ ] Ghi lại `rs.status()` (có replica set hay standalone)
- [ ] Branch riêng cho từng phase (không sửa lẫn P1/P2 trên cùng PR nếu có thể)

---

## Phase 1 — Cluster control ổn định (P0/P1 blocking)

Mục tiêu: STOP rồi RUN lại mà pairing/dispatch vẫn sống; lệnh cluster không bị mất.

### #1 — Publisher/consumer/dispatcher chết sau STOP (P0)

- [x] **Phân tích:** `orchestrator.py` — `_is_running = _running and not _paused`; loop `while is_running()` thoát khi pause
- [x] Tách `_alive` (vòng đời task) khỏi `_paused` (tạm dừng nghiệp vụ)
- [x] Loop: `while _alive:` → nếu `_paused` thì `sleep` + `continue`, không `return`
- [x] `pause()` chỉ set `_paused=True`; `resume()` set `_paused=False`, **không** recreate task nếu đã alive
- [x] `stop()` mới set `_alive=False` và cancel task
- [ ] Kiểm: STOP → đợi 5s → RUN → vẫn có start event mới (T1) — **cần chạy trên máy thật**

**File:** `src/pairing_orchestrator/orchestrator.py`, `publisher.py`, `mongo_pool.py`, `dispatcher.py`, `distributed_dispatcher.py`  
**Test:** T1  
**Sửa code:** 2026-10-14 — tách `_alive`/`_paused`; publisher/dispatcher sleep khi pause; consumer vẫn sync pool khi pause

### #2 — Dispatch lệnh từ state cũ ngay khi RUN (P0)

- [x] **Phụ thuộc #1** (chỉ lộ rõ sau khi #1 xong)
- [x] Reset / clear `ready_start_list`, `ready_end_list` và timer điểm khi nhận RUN
- [x] Thêm delay ổn định (2–3s) trước khi dispatcher gửi ICS lần đầu sau RUN
- [ ] Kiểm: STOP dài → RUN không bắn lệnh ảo từ state cũ — **cần chạy trên máy thật**

**Kịch bản kiểm (ngắn):**
1. Worker đang RUN; để xe đứng ở một `start_*` ~20s (chưa đủ 30s) hoặc đã ready.
2. `POST /engine-control/stop-all` → đợi **≥ 60s** (STOP dài).
3. `POST /engine-control/start-all` → quan sát 0–10s đầu.
4. **Đạt:** không có start event / ICS mới ngay lập tức từ điểm cũ; log có reset ready + stabilize ~3s; điểm phải đếm lại đủ 30s sau khi camera ổn mới ready.
5. **Không đạt:** ngay sau RUN đã có event/ICS cho điểm đã thấy trước lúc STOP.

**File:** `src/inference_engine/state_manager.py`, `orchestrator.py` / cluster listener  
**Test:** T1  
**Sửa code:** 2026-10-14 — `reset_ready_state_for_run()` + `RESUME_STABILIZE_SECONDS=3` trong `resume()`


### #3 — RUN cluster clear zone/node đang khóa tay (P0)

- [x] **Phụ thuộc #1**
- [x] `resume()` không gọi `_disabled_nodes.clear()` / `_disabled_areas.clear()` khi RUN từ cluster
- [ ] (Khuyến nghị) Lưu lock zone vào Mongo dùng chung để mọi worker cùng thấy — **chưa làm**
- [x] Zone-stop local vẫn hoạt động; RUN cluster không mở lại zone đã khóa
- [ ] Kiểm: khóa zone → STOP/RUN cluster → zone vẫn khóa (T1) — **cần chạy trên máy thật**

**Kịch bản kiểm (ngắn):**
1. `POST /engine-control/{zone}/stop-all` (vd. AE5) → zone bị khóa pairing.
2. `POST /engine-control/stop-all` rồi `POST /engine-control/start-all` (STOP/RUN cluster).
3. **Đạt:** zone vẫn không ghép cặp / không POST ICS cho node thuộc zone đó; chỉ mở lại khi `POST /engine-control/{zone}/start-all`.
4. **Không đạt:** sau RUN cluster, zone đã khóa lại gửi được lệnh ICS.

**File:** `src/pairing_orchestrator/orchestrator.py`, listener / API zone  
**Test:** T1  
**Sửa code:** 2026-10-14 — bỏ `clear()` disabled trong `resume()`; mở khóa chỉ qua `enable_*`

### #9 — Change stream chết im lặng, không đối soát (P1)

- [x] Luôn chạy vòng poll định kỳ (vd. 5s) song song / làm nguồn sự thật
- [x] Stream chỉ để giảm độ trễ; stream kết thúc không được thoát listener
- [x] Wrap `_watch_loop` trong vòng retry vô hạn khi `_running`
- [x] Giám sát task listener; lỗi thì log WARNING + restart loop
- [x] `get_current_status` → `None` khi lỗi đọc; poll/bootstrap skip (không giả STOP/token=0)
- [ ] Kiểm: đóng stream / lỗi stream → lệnh mới vẫn được áp dụng (T7) — **cần chạy trên máy thật**

**Kịch bản kiểm (ngắn):**
1. Worker đang chạy; gây change stream đóng/lỗi (restart mongod secondary, hoặc ngắt mạng ngắn tới Mongo).
2. Gửi `POST /engine-control/stop-all` hoặc `start-all`.
3. **Đạt:** trong ≤ ~5s (poll) worker vẫn apply lệnh; log có reconnect stream / poll apply; listener không chết im.
4. **Không đạt:** sau khi stream chết, lệnh mới không bao giờ được apply cho đến khi restart worker.

**File:** `src/load_balancing/cluster_control_listener.py`, `mongo_cluster_control_client.py`  
**Test:** T7  
**Sửa code:** 2026-10-14 — poll 5s + stream retry; status `None` khi lỗi đọc (không STOP giả)

### #10 — Token reset về nhỏ hơn bị bỏ qua (P1)

- [x] Đổi điều kiện `token > last_applied` → `token != last_applied` (hoặc thêm epoch)
- [x] Khi `token < last_applied` log WARNING
- [ ] Kiểm: xóa doc `engine_control_status` → gửi lệnh mới → mọi worker áp dụng (T5) — **cần chạy trên máy thật**

**Kịch bản kiểm (ngắn):**
1. Worker đã apply vài lệnh (token cao, vd. 10).
2. Xóa doc: `db.engine_control_status.deleteOne({_id:"inference_status"})`.
3. Gửi lại `stop-all` hoặc `start-all` (token mới bắt đầu từ 1).
4. **Đạt:** mọi worker apply lệnh mới; log WARNING token đi lùi rồi vẫn apply.
5. **Không đạt:** worker bỏ qua vì `1 < last_applied`.

**File:** `src/load_balancing/cluster_control_listener.py`  
**Test:** T5  
**Sửa code:** 2026-10-14 — apply khi `token != last_applied`; WARNING nếu token nhỏ hơn

### Checklist đóng Phase 1

- [ ] T1 đạt
- [ ] T5 đạt
- [ ] T7 đạt
- [ ] Không còn AttributeError / crash khi STOP↔RUN nhiều lần
- [ ] Code review + merge

---

## Phase 2 — Failover camera động (P0/P1)

Mục tiêu: worker chết → camera mồ côi được máy khác **thật sự decode**, không cần restart.

### #5 — Chia khối liên tiếp → đổi chủ quá nhiều (P0)

- [x] Đổi thuật toán: **giữ chủ cũ**, chỉ chia camera mồ côi
- [x] Máy quay lại: lấy bớt từ máy tải cao nhất (minimize move)
- [x] So sánh số liệu với sheet `Số liệu chia camera` (w1 sập không còn ~41 đổi chủ) — unit: w1 sập đổi chủ = 20 (không 41)
- [x] Unit test cho `calculate_assignment*` với 78 camera / 4 worker
- [ ] Kiểm T2/T6 trên cluster thật (cần kèm #4 hot-apply mới thấy decode)

**Kịch bản kiểm (ngắn):**
1. 4 worker đã chia camera; ghi `current_worker` trước khi test.
2. Kill w1 → đợi heartbeat timeout + 1 chu kỳ.
3. **Đạt (DB):** chỉ ~20 camera của w1 đổi `current_worker`; w2/w3/w4 giữ camera cũ.
4. **Không đạt:** ~41 camera đổi chủ (thuật toán khối cũ).
5. Start lại w1 → số camera chuyển về w1 ~19–20 (không xếp lại cả 78).

**File:** `src/load_balancing/camera_assignment_service.py`, `worker_manager.py`  
**Test:** T2, T6 — unit: `unit_test/test_camera_assignment_minimize_move.py`  
**Sửa code:** 2026-10-14 — `calculate_minimize_move_assignment` + `get_current_ownership`

### #8 — Chỉ so số lượng worker, thiếu debounce (P0)

- [x] So sánh `set(worker_id)` thay vì chỉ `len`
- [x] So sánh `set(camera_id)` để phát hiện camera mới trong DB
- [x] Worker chỉ coi là chết sau **N** lần thiếu heartbeat liên tiếp (debounce)
- [ ] Kiểm: thay worker_id / thêm camera → có rebalance đúng lúc — **cần chạy trên máy thật**

**Kịch bản kiểm (ngắn):**
1. 4 worker đang chạy; thêm 1 camera vào `node_id` → trong 1–2 chu kỳ heartbeat phải có worker claim camera mới.
2. (Tuỳ chọn) Restart lệch pha w3/w4 sao cho `len` tạm = 3 nhưng thành viên khác → vẫn rebalance đúng orphan.
3. Giật mạng ngắn 1 chu kỳ: không được chia camera ngay (debounce N=2).

**File:** `src/load_balancing/worker_manager.py`  
**Test:** T2  
**Sửa code:** 2026-10-14 — so `frozenset` worker/camera; `dead_miss_threshold=2`

### #7 — Lỗi Mongo hiểu nhầm thành “không còn worker/camera” (P0)

- [x] `get_active_workers` lỗi → ném / trả `unknown`, **không** `return []`
- [x] `validate_token` lỗi → không coi như mất quyền sở hữu
- [x] Caller: log WARNING + **bỏ qua** lần rebalance đó
- [ ] Kiểm: kill mongod primary → không release hàng loạt camera (T3) — **cần chạy trên máy thật**

**Kịch bản kiểm (ngắn):**
1. Cluster đang RUN ổn định.
2. Kill mongod primary (hoặc ngắt mạng Mongo ngắn) trong lúc bầu cử.
3. **Đạt:** log `unknown` / skip rebalance; `current_worker` không bị release hàng loạt.
4. **Không đạt:** nhiều camera `current_worker=null` hoặc đổi chủ loạn trong lúc DB lỗi.

**File:** `src/load_balancing/worker_registry_service.py`, `camera_assignment_service.py`, `worker_manager.py`  
**Test:** T3  
**Sửa code:** 2026-10-14 — API trả `None` = unknown; skip rebalance / giữ ownership

### #4 — Rebalance DB nhưng không hot-apply CameraManager (P0) ⭐ then chốt

- [x] **Phụ thuộc #5, #7, #8**
- [x] Thêm `CameraManager.add_camera(config)` / `remove_camera(camera_id)`
- [x] Đổi `enabled` / `camera_zones` sang dict theo `cameraId` (không chỉ index)
- [x] Sau rebalance: claim → add thread; release → stop thread
- [x] Camera mới bật theo `desired_state` hiện tại (RUN/STOP)
- [x] `RuntimeService`: nối `WorkerManager` rebalance → apply lên `camera_manager`
- [x] Mỗi chu kỳ đối soát `get_managed_camera_ids()` ↔ `assigned_camera_ids` (add/remove chênh)
- [x] Fencing invalid: giữ assigned đến rebalance rồi `to_release` → `remove_camera`
- [ ] Kiểm: kill 1 worker → camera mồ côi chạy lại trên máy khác, không restart (T2) — **cần máy thật**

**Kịch bản kiểm (ngắn):**
1. Cluster RUN; kill w3 → đợi debounce + heartbeat.
2. **Đạt:** worker còn lại có thread/ffmpeg mới cho camera của w3; không cần restart process.
3. **Không đạt:** Mongo đã đổi `current_worker` nhưng không có decode mới.

**File:** `src/inference_engine/camera_manager.py`, `camera_processor.py`, `pairing_orchestrator/runtime_service.py`, `worker_manager.py`  
**Test:** T2, T6, T8  
**Sửa code:** 2026-10-14 — hot-add/remove + callback; 2026-10-14 — reconcile managed vs assigned mỗi chu kỳ

### #15 — Fencing token ghi nhưng không từ chối worker cũ (P1)

- [x] **Nên làm sau #4**
- [x] `claim_ready` / publish kiểm token khớp `node_id.fencing_token`
- [x] Token lệch → từ chối thao tác worker cũ
- [ ] Kiểm: sau rebalance, worker cũ không còn claim được start event của camera đã mất — **cần máy thật**

**Kịch bản kiểm (ngắn):**
1. Sau failover, worker cũ vẫn còn process (nếu chưa chết hẳn) cố publish/claim camera đã mất.
2. **Đạt:** `upsert_ready` / `claim_ready` reject (log ownership/fencing); không POST ICS từ worker cũ.

**File:** `src/pairing_orchestrator/persistence/mongo_start_event_client.py`  
**Test:** T2  
**Sửa code:** 2026-10-14 — kiểm `current_worker` + `fencing_token` khi upsert/claim

### #6 — Đồng hồ local lệch giữa máy (P0)

- [x] Heartbeat / cutoff / `claim_until` dùng giờ server (`$$NOW` hoặc pipeline tương đương)
- [x] Hướng dẫn đồng bộ giờ Windows (`w32tm`) trên 4 máy
- [ ] Kiểm: lệch giả +40s không ping-pong camera (T4) — **cần máy thật**
- [x] Nếu Mongo &lt; 4.2: ghi rõ workaround thay `$$NOW`

**Yêu cầu Mongo:** aggregation `$$NOW` cần **MongoDB ≥ 4.2**. Nếu thấp hơn: nâng Mongo hoặc tạm dùng `datetime.utcnow()` + đồng bộ NTP chặt.

**Đồng bộ giờ Windows (khuyến nghị thêm):**
```bat
w32tm /resync /force
w32tm /query /status
```

**File:** `src/load_balancing/worker_registry_service.py`, `mongo_start_event_client.py`  
**Test:** T4  
**Sửa code:** 2026-10-14 — register/heartbeat/active cutoff + claim_until dùng `$$NOW`

### Checklist đóng Phase 2

- [ ] T2 đạt (failover thật)
- [ ] T3 đạt (primary election không drop camera)
- [ ] T4 đạt (lệch giờ)
- [ ] T6 đạt (máy quay lại, move tối thiểu)
- [ ] T8 đạt (STOP/RUN lặp không leak ffmpeg)
- [ ] Code review + merge

---

## Phase 3 — Vận hành & polish (P1/P2/P3)

Có thể làm song song / sau Phase 1–2.

### API / bảo mật

#### #11 — `expected_workers: 4` cứng; ack che lỗi engine (P1)

- [ ] Lấy số worker từ registry
- [ ] Ack kèm: số camera sống, trạng thái engine, số task pairing còn chạy
- [ ] Không `except: pass` nuốt lỗi trong `InferenceEnginePool.pause/resume` khi ack

**File:** `src/api/routes/cameras.py`, `src/inference_engine/inference_engine_pool.py`

#### #12 — `/runtime/reload` AttributeError `AREA_NAME` (P1)

- [x] Bỏ tham chiếu `AREA_NAME` trong `runtime.py` / settings
- [ ] Kiểm: `POST /runtime/reload` không `?area=` không crash — **cần chạy**

**File:** `src/api/settings.py`, `src/api/routes/runtime.py`  
**Sửa code:** 2026-10-14 — `POST /runtime/reload` không còn đọc `settings.AREA_NAME`

#### #13 — Không auth, CORS `*` (P1)

> **Làm rõ:** CORS **không thiếu** — `app_factory` đã có `CORSMiddleware` với `allow_origins=["*"]` (quá mở). Lỗi thật là **thiếu auth** trên `/engine-control` (máy nào trong LAN cũng STOP/RUN được).

- [ ] API key hoặc allow-list IP cho `/engine-control`
- [ ] Thu hẹp CORS (bỏ `*`) + body JSON để trình duyệt buộc preflight (khi siết origin)
- [ ] Kiểm: request không key bị từ chối

**File:** `src/api/app_factory.py`, routes engine-control  
**Trạng thái:** chưa làm (cần quyết định API key / IP allow-list)

### Camera / decoder

#### #14 — RUN tạo nhiều ffmpeg cùng lúc; thiếu timeout RTSP (P1)

- [x] Jitter start theo worker + camera
- [x] Probe ffmpeg 1 lần: ≥5 dùng `-timeout`, cũ dùng `-stimeout` (+ luôn `-rw_timeout`; không truyền cả hai)
- [ ] Sau nhiều chu kỳ STOP/RUN: kiểm `tasklist | findstr ffmpeg` không tăng dần — **T8 máy thật**
- [ ] Test: T8

**File:** `src/inference_engine/camera_processor.py`, `gpu_video_decoder.py`, `config.py`  
**Sửa code:** 2026-10-14 — jitter 0..2.5s; RTSP timeout 5s; probe chọn timeout flag

#### #21 — 26 cam/máy vs batch 24 + hold_full_batch (P2)

- [ ] Đo GPU / NVDEC / RTSP ở mức 26 cam/máy sau failover
- [ ] Điều chỉnh batch / `hold_full_batch` nếu cần (sau khi #4 xong)

**File:** `src/config.py`, inference path  
**Test:** đo trên máy thật

### Log / Mongo / code nhỏ

#### #17 — Console QuickEdit treo heartbeat (P2)

- [ ] `AI_LOG_LEVEL=warning` hoặc `access_log=False`
- [ ] Runbook: tắt QuickEdit trên console worker
- [ ] Test: T9

**File:** `src/apps/main.py` (hoặc entrypoint uvicorn), runbook

#### #18 — Log ngày cố định, DEBUG, lẫn 4 worker (P2)

- [x] Đưa `WORKER_ID` vào đường dẫn log (`logs/{WORKER_ID}/...`)
- [x] TimedRotatingFileHandler (midnight, giữ 7 ngày); default level INFO

**File:** `src/shared/setup_log.py`  
**Sửa code:** 2026-10-14 — path theo worker + rotate theo ngày

#### #19 — Log nguyên MongoDB URL (có thể có password) (P2)

- [x] **Bỏ qua** (theo quyết định 2026-10-14) — không che URL trong log lúc này

**File:** `src/persistence/database.py`

#### #16 — Replica votes / URL (P1 hạ tầng)

- [x] Env sẵn: `MongoDB_URL`, `MONGO_REPLICA_SET`, `MONGO_PREFERRED_PRIMARY_HOST`, `MONGO_VOTING_MEMBER_HOSTS` (product chỉ đổi giá trị)
- [ ] `rs.reconfig` trên cluster: 1 primary ưu tiên + 3 voting (IP product cung cấp sau)
- [ ] Hostname/IP resolve được từ cả 4 máy

**File:** `src/core/settings.py`, `.env.example`, cấu hình Mongo runtime

#### #20 — Không watchdog; TensorRT path máy cứng (P2)

- [ ] NSSM / Task Scheduler auto-restart worker — **làm sau**
- [x] Bỏ hard path `D:/TensorRT-...` khỏi `requirements.txt`
- [ ] 4 máy cùng GPU/driver/TensorRT hoặc build `.engine` riêng từng máy (triển khai)

**File:** triển khai, `requirements.txt`

#### #22 — `datetime.utcnow()` deprecated + cộng tay +7h (P3)

- [x] Cluster control: `datetime.now(timezone.utc)`, không cộng tay +7 khi ghi DB
- [ ] Quét chỗ còn `utcnow` (registry, assignment, start_event, node_id) — format VN chỉ ở UI/API

**File:** `mongo_cluster_control_client.py`, registry, …

#### #23 — `return_document=True` (P3)

- [x] `ReturnDocument.AFTER` trong `find_one_and_update`

**File:** `src/load_balancing/persistence/mongo_cluster_control_client.py`

#### #24 — Thiếu unique index `(worker_id, token)` trên acks (P3)

- [x] `ensure_indexes()` + gọi từ `ClusterControlListener.start()`

**File:** `mongo_cluster_control_client.py`, `cluster_control_listener.py`

#### #25 — Collection `start_events_test` dùng production (P3)

- [x] `START_EVENTS_COLLECTION` trong settings / `.env` (mặc định `start_events`)

**File:** `settings.py`, `mongo_start_event_client.py`, `orchestrator.py`

#### #26 — `stop()` không clear `api_state.pairing_orchestrator` (P3)

- [x] `api_state.set_pairing_orchestrator(None)` trong `RuntimeService.stop()`

**File:** `src/pairing_orchestrator/runtime_service.py`

### Checklist đóng Phase 3

- [ ] #11–#13 xong
- [ ] #14, #17–#21 xong hoặc có runbook đo máy thật
- [ ] #16, #20 có checklist hạ tầng đã thực hiện trên cluster
- [ ] #22–#26 xong
- [ ] T8, T9 đạt (nếu liên quan)

---

## Bảng map Test (từ Excel)

| Mã | Lỗi liên quan | Kịch bản ngắn | Đạt? |
|----|---------------|---------------|------|
| T1 | 1, 2, 3 | stop-all → đợi 5s → start-all | ☐ |
| T2 | 4, 5, 7, 8 | Kill 1 worker (+ mongod của nó); camera mồ côi chạy lại | ☐ |
| T3 | 7 | Kill mongod primary; không release camera hàng loạt | ☐ |
| T4 | 6 | Lệch giờ +40s; không rebalance sai | ☐ |
| T5 | 10 | Xóa `engine_control_status` → lệnh mới vẫn apply | ☐ |
| T6 | 4, 5 | Worker quay lại 3→4; move ~ tối thiểu | ☐ |
| T7 | 9 | Stream chết; listener vẫn apply nhờ poll | ☐ |
| T8 | 14 | STOP/RUN ≥20 lần; ffmpeg/VRAM không leak | ☐ |
| T9 | 17 | Click console 60s; heartbeat không dừng | ☐ |

---

## Thứ tự khuyến nghị (đừng đảo lung tung)

```
Phase 1:  #1 → #2 → #3
          #9, #10 (song song được)

Phase 2:  #5, #8, #7  →  #4  →  #15, #6

Phase 3:  #12, #26 (nhanh) → còn lại tùy ưu tiên vận hành
```

**Giải thích thuật ngữ**

- **Failover:** khi 1 worker chết, worker khác nhận camera của nó.
- **Hot-apply:** thêm/bớt camera đang chạy mà không restart process.
- **Fencing token:** số phiên sở hữu camera; tăng khi claim để chặn worker cũ.
- **Change stream:** Mongo đẩy event khi collection đổi (cần replica set); không có thì poll.

---

## Ghi chú cập nhật

| Ngày | Nội dung |
|------|----------|
| 2026-10-14 | Tạo checklist từ Excel + đối chiếu code (26/26 còn đúng) |
| 2026-10-14 | Sửa lỗi #1: tách `_alive` / `_paused` cho pairing loops |
| 2026-10-14 | Sửa lỗi #2: reset ready/timer khi RUN + delay stabilize 3s |
| 2026-10-14 | Sửa lỗi #3: `resume()` không clear zone/node lock; thêm kịch bản kiểm #2/#3 |
| 2026-10-14 | Sửa lỗi #9/#10: poll đối soát + token `!=` / WARNING khi lùi |
| 2026-10-14 | Sửa lỗi #5: minimize-move assignment + unit test 78 cam |
| 2026-10-14 | Sửa lỗi #7/#8: Mongo unknown + set compare + debounce |
| 2026-10-14 | Phase 2 còn lại: #4 hot-apply, #15 fencing, #6 $$NOW |
| 2026-10-14 | #12 bỏ AREA_NAME; #14 jitter+RTSP timeout; #18 log theo worker |
| 2026-10-14 | Env Mongo/replica; bỏ TensorRT path; #23–#26; watchdog để sau |
| 2026-10-14 | FFmpeg probe timeout flag; status None khi Mongo lỗi; reconcile CameraManager |
