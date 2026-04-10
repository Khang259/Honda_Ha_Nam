"""
Service để load validate pairs từ MongoDB và convert sang format runtime.
"""

from __future__ import annotations
from typing import Optional, Set, Tuple

from api.clients.mongo_pair_client import MongoPairClient
from utils.setup_log import setup_logger

logger = setup_logger("validate_pairs_service", "logs/validate_pairs_service/log")


class ValidatePairsService:
    """Service load validate pairs từ MongoDB và convert sang set[tuple]."""

    def __init__(self, client: Optional[MongoPairClient] = None):
        self._client = client or MongoPairClient()

    async def get_validate_pairs(self, area: str) -> Set[Tuple[str, ...]]:
        """
        Load validate pairs từ MongoDB theo area, convert sang set[tuple].
        
        Args:
            area: Tên area (vd: AE5, AE6)
            
        Returns:
            Set các tuple:
            - Normal pair: (start, end)
            - Empty car: (start,)
        """
        docs = await self._client.get_pairs_by_area(area)
        validate_pairs = self._convert_to_tuples(docs)
        logger.info(f"Loaded {len(validate_pairs)} pairs for area {area}")
        return validate_pairs

    async def get_validate_pairs_all(self) -> Set[Tuple[str, ...]]:
        """
        Load tất cả validate pairs (không filter area).
        
        Returns:
            Set các tuple (start,) hoặc (start, end)
        """
        docs = await self._client.get_all_pairs()
        validate_pairs = self._convert_to_tuples(docs)
        logger.info(f"Loaded {len(validate_pairs)} pairs (all areas)")
        return validate_pairs

    def _convert_to_tuples(self, docs: list) -> Set[Tuple[str, ...]]:
        """
        Convert list[dict] từ MongoDB sang set[tuple] cho runtime.
        
        Format MongoDB: {start: str, end: str|None, area_name: str, ...}
        Format runtime: set[(start, end)] hoặc set[(start,)]
        """
        result = set()
        for doc in docs:
            if not isinstance(doc, dict):
                continue
                
            start = doc.get("start")
            if not start:
                continue
                
            end = doc.get("end")
            if end is None:
                # Xe trống: tuple 1 phần tử
                result.add((start,))
            else:
                # Normal pair: tuple 2 phần tử
                result.add((start, end))
        
        return result


# Singleton instance
validate_pairs_service = ValidatePairsService()
