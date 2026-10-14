"""Seed collection end_points (cần ≥1 doc khi RuntimeService.start)."""

from __future__ import annotations

import os
import sys

from pymongo import MongoClient

# Cho phép chạy từ root project
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from api.settings import settings  # noqa: E402


def main() -> None:
    client = MongoClient(settings.MongoDB_URL, serverSelectionTimeoutMS=8000)
    db = client[settings.MongoDB_DB]

    pair = db.validate_pairs.find_one({"end": {"$exists": True, "$ne": None}})
    end_name = pair["end"] if pair else "end_10000760"

    doc = {"end_points": end_name, "empty_car": False}
    result = db.end_points.update_one(
        {"end_points": end_name},
        {"$set": doc},
        upsert=True,
    )
    print(
        f"OK end_points: {doc} "
        f"(upserted={result.upserted_id}, matched={result.matched_count})"
    )


if __name__ == "__main__":
    main()
