"""Ghép cặp local (FIFO) và hàng chờ empty (15s) — cùng logic PairManager.make_pairs."""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Set, Tuple

from inference_core.state_manager import StateManager
from shared.data import payload_sent_ICS


def enqueue_empty_pending(
    state: StateManager,
    validate_pairs: Set[Tuple[str, ...]],
    pending_empty: List[Tuple[str, float]],
    now: float,
    empty_deadline_offset: float = 15.0,
) -> None:
    ready = set(state.snapshot_ready_starts())
    for pair in validate_pairs:
        if len(pair) != 1:
            continue
        start_empty = pair[0]
        if start_empty not in ready:
            continue
        if not any(start_empty == item[0] for item in pending_empty):
            pending_empty.append((start_empty, now + empty_deadline_offset))


def make_normal_pairs_local(
    state: StateManager,
    validate_pairs: Set[Tuple[str, ...]],
) -> Tuple[List[Tuple[str, str]], List[Dict[str, Any]]]:
    """Cặp (start, end) khi cả hai đều ready trên worker này; payload single ICS."""
    pairs: List[Tuple[str, str]] = []
    payloads: List[Dict[str, Any]] = []
    used_starts: set = set()
    used_ends: set = set()
    ready_ends = set(state.snapshot_ready_ends())
    start_queue = deque(state.snapshot_ready_starts())
    while start_queue:
        start_point = start_queue.popleft()
        if start_point in used_starts:
            continue
        candidate_end = None
        for p in validate_pairs:
            if len(p) != 2:
                continue
            s, e = p[0], p[1]
            if s != start_point:
                continue
            if e in ready_ends and e not in used_ends:
                candidate_end = e
                break
        if candidate_end is None:
            continue
        pairs.append((start_point, candidate_end))
        payloads.append(payload_sent_ICS(start_point, candidate_end))
        used_starts.add(start_point)
        used_ends.add(candidate_end)
    return pairs, payloads
