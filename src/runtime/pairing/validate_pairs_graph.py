"""Ánh xạ end_node -> danh sách start hợp lệ (từ validate_pairs)."""

from __future__ import annotations

from typing import Dict, List, Set, Tuple


def build_end_to_starts(validate_pairs: Set[Tuple[str, ...]]) -> Dict[str, List[str]]:
    end_to_starts: Dict[str, List[str]] = {}
    for p in validate_pairs:
        if len(p) != 2:
            continue
        s, e = p[0], p[1]
        end_to_starts.setdefault(e, []).append(s)
    return end_to_starts
