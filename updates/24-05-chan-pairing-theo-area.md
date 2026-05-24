# 24-05 — Chặn pairing theo area

## Tóm tắt thay đổi

Bổ sung logic chặn POST ICS theo `area_name`, song song với `disabled_nodes`.

| Loại pair | Điều kiện chặn |
|-----------|----------------|
| Normal (single, double) | node disabled OR `area(start) ∈ disabled_areas` OR `area(end) ∈ disabled_areas` |
| Empty | node start disabled OR `area(start) ∈ disabled_areas` (không check end) |

**Files:** `orchestrator.py`, `dispatcher.py`, `distributed_dispatcher.py`, `cameras.py`

---

## Quyết định ngoài spec

- **Giữ cả disabled_nodes + disabled_areas:** User chọn "both" — stop zone gọi cả hai.
- **Load `end_to_area`:** Map end node → area từ Mongo pair docs (fallback `end_area = start_area`).
- **Zone uppercase = area name:** `disable_areas({zone.upper()})` — giả định zone camera = `area_name` MongoDB.
- **Duplicate should_post trong 2 dispatcher class:** Không extract helper chung.

## Thay đổi so với yêu cầu

| Yêu cầu | Thực tế |
|---------|---------|
| Chặn area(start) hoặc area(end) | Đúng — local + distributed |
| Empty chỉ check area(start) | Đúng — `_should_post_empty` riêng |
| Thay thế disabled_nodes | **Không** — giữ song song |
| API stop zone → disable area | Đúng — `disable_areas({z})` |

## Trade-off

| Ưu | Nhược |
|----|-------|
| Chặn cross-zone đúng (start AE5 + end SUB5) | Redundant nếu node map đã đúng |
| Empty rule rõ ràng | Pop pending_empty khi blocked → mất event |
| Area map load 1 lần lúc startup | Pair mới trong Mongo cần restart orchestrator |

## Review / workflow / dataflow

```
POST /AE5/stop-all → disable_areas({"AE5"})

_should_post_pair(start, end):
  1. start/end in disabled_nodes? → block
  2. area(start) or area(end) in disabled_areas? → block
  3. else → POST

_should_post_empty(start, end):
  1. start in disabled_nodes? → block
  2. area(start) in disabled_areas? → block
  3. else → POST
```

**Scenarios quan trọng:**

| Scenario | Kỳ vọng |
|----------|---------|
| Stop AE5, pair start AE5 + end SUB5 | Block (area start) |
| Stop AE5, pair start SUB5 + end AE5 | Block (area end) |
| Stop AE5, empty start SUB5 | Vẫn POST (chỉ check start) |

**Checklist:** `end_to_area` load lúc start; `resume()` clear `_disabled_areas`; empty paths dùng `_should_post_empty`.

**Known gaps:** Zone name ≠ area_name trong data; pair map stale until restart.
