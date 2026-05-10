"""Chạy API server: thêm src/ vào sys.path rồi gọi apps.main."""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from apps.main import main

if __name__ == "__main__":
    main()
