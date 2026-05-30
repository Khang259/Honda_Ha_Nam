# scripts/push_validate_pairs.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pymongo import MongoClient

from api.settings import settings
from config import PAIRS_AE_5, PAIRS_AE_6


PairTuple = Tuple[str, ...]


def to_mongo_pairs(pairs: Sequence[PairTuple]) -> List[Dict[str, Optional[str]]]:
    out: List[Dict[str, Optional[str]]] = []
    for t in pairs:
        if not t:
            continue
        start = str(t[0])
        end = str(t[1]) if len(t) > 1 and t[1] is not None else None
        out.append({"start": start, "end": end})
    return out


def upsert_zone(col, zone: str, pairs: Sequence[PairTuple]) -> None:
    doc: Dict[str, Any] = {
        "zone": zone.upper(),
        "pairs": to_mongo_pairs(pairs),
        "updated_at": datetime.now(timezone.utc),
    }

    col.update_one(
        {"zone": doc["zone"]},
        {"$set": doc, "$setOnInsert": {"created_at": doc["updated_at"]}},
        upsert=True,
    )


def main() -> None:
    mongodb_url = settings.MongoDB_URL
    db_name = settings.MongoDB_DB
    collection_name = "validate_pairs"

    client = MongoClient(mongodb_url, connectTimeoutMS=2000, serverSelectionTimeoutMS=2000)
    try:
        db = client[db_name]
        col = db[collection_name]

        # (tuỳ chọn) index để đảm bảo unique theo zone
        col.create_index("zone", unique=True)

        upsert_zone(col, "AE5", PAIRS_AE_5)
        upsert_zone(col, "AE6", PAIRS_AE_6)

        print(f"Upserted validate pairs into {db_name}.{collection_name}: AE5, AE6")
    finally:
        client.close()


if __name__ == "__main__":
    main()