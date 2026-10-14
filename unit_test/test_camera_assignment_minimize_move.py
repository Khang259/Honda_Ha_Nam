"""Unit test thuật toán minimize-move (lỗi #5) — không cần Mongo/FastAPI."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
MODULE_PATH = SRC / "load_balancing" / "camera_assignment_service.py"

sys.modules.setdefault("persistence", MagicMock())
sys.modules.setdefault("persistence.database", MagicMock())
sys.modules.setdefault("shared", MagicMock())
sys.modules.setdefault("shared.setup_log", MagicMock())

_spec = importlib.util.spec_from_file_location(
    "camera_assignment_service_under_test",
    MODULE_PATH,
)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
CameraAssignmentService = _mod.CameraAssignmentService


def _owners_from_assignment(assignment: Dict[str, List[int]]) -> Dict[int, Optional[str]]:
    owners: Dict[int, Optional[str]] = {}
    for worker_id, cams in assignment.items():
        for cam_id in cams:
            owners[cam_id] = worker_id
    return owners


def _changed_owners(
    before: Dict[int, Optional[str]],
    after: Dict[str, List[int]],
) -> int:
    after_owners = _owners_from_assignment(after)
    return sum(1 for cam_id, owner in after_owners.items() if before.get(cam_id) != owner)


def test_cold_start_balances_evenly():
    cams = list(range(78))
    workers = ["w1", "w2", "w3", "w4"]
    result = CameraAssignmentService.calculate_minimize_move_assignment(
        cams, workers, current_owners=None
    )
    counts = sorted(len(v) for v in result.values())
    assert counts == [19, 19, 20, 20]
    assert sum(len(v) for v in result.values()) == 78


def test_worker_down_only_moves_orphans():
    cams = list(range(78))
    workers4 = ["w1", "w2", "w3", "w4"]
    initial = CameraAssignmentService.calculate_contiguous_assignment_for_camera_ids(
        cams, workers4
    )
    owners = _owners_from_assignment(initial)

    alive = ["w2", "w3", "w4"]
    after = CameraAssignmentService.calculate_minimize_move_assignment(
        cams, alive, current_owners=owners
    )

    orphan_ids: Set[int] = set(initial["w1"])
    changed = _changed_owners(owners, after)

    for w in alive:
        kept = set(initial[w]) & set(after[w])
        assert kept == set(initial[w]), f"{w} lost sticky cameras"

    assert changed == len(orphan_ids)
    assert changed == 20

    contiguous_after = CameraAssignmentService.calculate_contiguous_assignment_for_camera_ids(
        cams, alive
    )
    contiguous_changed = _changed_owners(owners, contiguous_after)
    assert contiguous_changed > changed
    assert contiguous_changed == 41


def test_worker_back_takes_from_richest():
    cams = list(range(78))
    workers4 = ["w1", "w2", "w3", "w4"]
    initial = CameraAssignmentService.calculate_contiguous_assignment_for_camera_ids(
        cams, workers4
    )
    owners = _owners_from_assignment(initial)

    after_3 = CameraAssignmentService.calculate_minimize_move_assignment(
        cams, ["w2", "w3", "w4"], current_owners=owners
    )
    owners_3 = _owners_from_assignment(after_3)

    after_4 = CameraAssignmentService.calculate_minimize_move_assignment(
        cams, workers4, current_owners=owners_3
    )
    counts = sorted(len(v) for v in after_4.values())
    assert counts == [19, 19, 20, 20]

    changed = _changed_owners(owners_3, after_4)
    assert 19 <= changed <= 26


def test_w3_down_moves_about_orphan_count():
    cams = list(range(78))
    workers4 = ["w1", "w2", "w3", "w4"]
    initial = CameraAssignmentService.calculate_contiguous_assignment_for_camera_ids(
        cams, workers4
    )
    owners = _owners_from_assignment(initial)
    orphan_count = len(initial["w3"])

    after = CameraAssignmentService.calculate_minimize_move_assignment(
        cams, ["w1", "w2", "w4"], current_owners=owners
    )
    changed = _changed_owners(owners, after)
    assert changed == orphan_count == 19
