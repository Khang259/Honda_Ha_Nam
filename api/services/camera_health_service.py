"""Kiểm tra TCP tới host:port từ URL RTSP (Mongo)."""

from __future__ import annotations

import asyncio
import socket
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

from api.clients.mongo_node_id_client import MongoNodeIdClient
from utils.setup_log import setup_logger

logger = setup_logger("camera_health_service", "logs/camera_health_service/log")

DEFAULT_CONNECT_TIMEOUT_S = 3.0


def _get_rtsp_url(doc: Dict[str, Any]) -> str:
    return (doc.get("url") or "").strip()


def _parse_host_port(rtsp_url: str) -> Tuple[str, int]:
    parsed = urlparse(rtsp_url)
    host = parsed.hostname
    if not host:
        raise ValueError("invalid_rtsp_url")
    port = parsed.port if parsed.port is not None else 554
    return host, port


def _tcp_probe(host: str, port: int, timeout_s: float) -> Tuple[bool, str]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout_s)
    try:
        sock.connect((host, port))
        return True, ""
    except TimeoutError:
        return False, "timeout"
    except OSError as e:
        return False, (e.strerror or str(e) or "connection_error")[:200]
    except Exception as e:
        return False, str(e)[:200]
    finally:
        try:
            sock.close()
        except OSError:
            pass


class CameraHealthService:
    async def check_area_all(self, timeout_s: float = DEFAULT_CONNECT_TIMEOUT_S) -> Dict[str, Any]:
        cameras = await MongoNodeIdClient().get_all()
        message: List[Dict[str, Any]] = []

        for doc in cameras:
            camera_id = doc.get("cameraId")
            rtsp = _get_rtsp_url(doc)

            if camera_id is None:
                message.append(
                    {
                        "cameraId": None,
                        "RTSP": rtsp or "",
                        "ok": False,
                        "error": "missing_cameraId",
                    }
                )
                continue

            if not rtsp:
                message.append(
                    {
                        "cameraId": camera_id,
                        "RTSP": "",
                        "ok": False,
                        "error": "missing_rtsp_url",
                    }
                )
                continue

            try:
                host, port = _parse_host_port(rtsp)
            except ValueError:
                message.append(
                    {
                        "cameraId": camera_id,
                        "RTSP": rtsp,
                        "ok": False,
                        "error": "invalid_rtsp_url",
                    }
                )
                continue

            ok, err = await asyncio.to_thread(_tcp_probe, host, port, timeout_s)
            entry: Dict[str, Any] = {"cameraId": camera_id, "RTSP": rtsp, "ok": ok}
            if not ok:
                entry["error"] = err or "unreachable"
            message.append(entry)

        return {"code": 1000, "checked": len(message), "message": message}


camera_health_service = CameraHealthService()