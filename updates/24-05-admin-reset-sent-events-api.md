# 24-05 — Admin API reset MongoDB sent events

## Tóm tắt thay đổi

API admin reset tất cả document `start_events_test` có `flag=True, status=sent` về `flag=False, status=pending`.

| API | Mô tả |
|-----|-------|
| `POST /admin/reset-sent-events` | Reset global, không filter worker |

**Files:** `mongo_start_event_client.py`, `admin.py`, `app_factory.py`

---

## Quyết định ngoài spec

- **Reset global:** Không filter theo `worker_id` — reset toàn collection matching điều kiện.
- **Không đụng RAM:** `StateManager.points` không được đồng bộ sau reset Mongo.
- **Unset claim fields:** Xóa `claim_owner`, `claim_until`, `sent_at`; thêm `admin_reset_at`.
- **Router prefix `/admin`:** Tách route admin riêng khỏi camera routes.

## Thay đổi so với yêu cầu

| Yêu cầu | Thực tế |
|---------|---------|
| Reset tất cả node flag=True, status=sent | Đúng — `update_many` không filter worker |
| Reset khi stop-all | **Không** — reset là API riêng, không gắn stop camera |

## Trade-off

| Ưu | Nhược |
|----|-------|
| Recovery khi worker crash / webhook fail | Ảnh hưởng mọi worker nếu chạy khi hệ thống đang active |
| Đơn giản, một lệnh fix stuck events | RAM flag có thể lệch với Mongo |
| Không cần biết worker nào giữ doc | Cần chạy khi idle hoặc đã stop pairing |

## Review / workflow / dataflow

```
POST /admin/reset-sent-events
  → MongoStartEventClient.reset_all_sent_to_pending()
  → update_many({flag: True, status: "sent"}, {$set: pending, $unset: claim...})
  → response {code: 1000, data: {count}}
```

**Khi nào dùng:** Worker chết giữ `status=sent`; webhook external không về; cần mở lại chu trình pairing.

**Checklist:** Response `1000/1001`; không filter worker; không sync StateManager.

**Log:** `logs/admin_routes/log`, `logs/mongo_start_event_client/log`
