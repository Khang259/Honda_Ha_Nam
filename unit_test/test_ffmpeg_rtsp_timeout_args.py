"""Unit test: chọn option timeout RTSP cho ffmpeg (không dùng -rw_timeout)."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from inference_engine.gpu_video_decoder import (  # noqa: E402
    reset_ffmpeg_rtsp_timeout_probe_cache,
    resolve_ffmpeg_rtsp_timeout_args,
)


@pytest.fixture(autouse=True)
def _clear_probe_cache():
    reset_ffmpeg_rtsp_timeout_probe_cache()
    yield
    reset_ffmpeg_rtsp_timeout_probe_cache()


def test_prefers_timeout_from_rtsp_demuxer_help():
    rtsp_help = """
  -timeout           <int64>      .D......... set timeout (in microseconds)
  -listen_timeout    <int>        .D......... set maximum timeout
"""
    with patch(
        "inference_engine.gpu_video_decoder._ffmpeg_help_text",
        return_value=rtsp_help,
    ):
        args = resolve_ffmpeg_rtsp_timeout_args("5000000")
    assert args == ["-timeout", "5000000"]
    assert "-rw_timeout" not in args


def test_falls_back_to_stimeout_when_only_stimeout_in_help():
    rtsp_help = """
  -stimeout          <int>        .D......... socket timeout (microseconds)
"""
    with patch(
        "inference_engine.gpu_video_decoder._ffmpeg_help_text",
        return_value=rtsp_help,
    ):
        args = resolve_ffmpeg_rtsp_timeout_args("5000000")
    assert args == ["-stimeout", "5000000"]


def test_never_includes_rw_timeout():
    rtsp_help = """
  -timeout           <int64>      .D......... set timeout
  -rw_timeout        <int64>      ED......... Timeout for IO operations
"""
    with patch(
        "inference_engine.gpu_video_decoder._ffmpeg_help_text",
        return_value=rtsp_help,
    ):
        args = resolve_ffmpeg_rtsp_timeout_args("1000")
    assert "-rw_timeout" not in args
    assert args[0] in ("-timeout", "-stimeout")


def test_caches_flag_but_uses_new_timeout_value():
    with patch(
        "inference_engine.gpu_video_decoder._ffmpeg_help_text",
        return_value="  -timeout           <int64>      .D......... x\n",
    ) as mock_help:
        a = resolve_ffmpeg_rtsp_timeout_args("1")
        b = resolve_ffmpeg_rtsp_timeout_args("999")
    assert a == ["-timeout", "1"]
    assert b == ["-timeout", "999"]
    assert mock_help.call_count == 1


def test_live_ffmpeg_probe_no_rw_timeout():
    """Chạy trên máy có ffmpeg trong PATH — đảm bảo không chọn rw_timeout."""
    args = resolve_ffmpeg_rtsp_timeout_args("5000000")
    assert len(args) == 2
    assert args[0] in ("-timeout", "-stimeout")
    assert args[1] == "5000000"
    assert "-rw_timeout" not in args
