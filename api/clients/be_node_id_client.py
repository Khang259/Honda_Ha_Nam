"""
HTTP client for BE /node_id APIs (camera config for AI runtime).
"""

from __future__ import annotations

from typing import Any, List, Union

import httpx


class BENodeIdClient:
    def __init__(self, base_url: str, timeout_s: float = 5.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_s

    @staticmethod
    def _parse_node_id_payload(data: Any) -> Union[dict, list]:
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data
        raise ValueError("BE /node_id response must be a JSON object or array")

    async def get_by_area(self, area_name: str) -> Union[dict, list]:
        url = f"{self._base_url}/node_id/{area_name}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return self._parse_node_id_payload(resp.json())

    async def get_all(self) -> List[dict]:
        url = f"{self._base_url}/node_id/all"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                raise ValueError("BE /node_id/all must return a JSON array")
            return [x for x in data if isinstance(x, dict)]
