"""HTTP client gửi lệnh tới ICS (external server)."""

from __future__ import annotations

from typing import Any, Dict

import requests

from shared.setup_log import setup_logger

logger = setup_logger("start_event_pairing", "logs/start_event_pairing/log")


class IcsClient:
    def __init__(self, ics_url: str, timeout_seconds: int = 30) -> None:
        self._url = ics_url
        self._timeout = timeout_seconds

    def post(self, payload: Dict[str, Any]) -> bool:
        try:
            response = requests.post(self._url, json=payload, timeout=self._timeout)
            if response.status_code != 200:
                logger.error("POST failed - status: %s", response.status_code)
                return False
            data = response.json()
            if data.get("code") == 1000:
                logger.debug("POST ok orderId=%s", payload.get("orderId"))
                return True
            logger.error("ICS error: %s", data)
            return False
        except Exception as e:
            logger.error("POST error: %s", e)
            return False
