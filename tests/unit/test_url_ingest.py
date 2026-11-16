"""Tests for the URL Intake Adapter (lib/url_ingest.py).

Validates URL scheme parsing, SSRF defense, disk headroom checking,
container remuxing, audio extraction fallback, source manifest emission,
and seamless handoff to lib/source_media_review.py.
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lib.url_ingest import (
    DiskSpaceError,
    MediaIngestionError,
    URLIngestResult,
    URLIntakeAdapter,
    URLValidationError,
    ensure_media_tools_on_path,
)
from tools.base_tool import ToolResult, ToolStatus


@pytest.fixture(autouse=True)
def setup_media_tools():
    """Ensure ffmpeg and ffprobe are available for tests."""
    ensure_media_tools_on_path()


@pytest.fixture
def adapter(tmp_path):
    """Create URLIntakeAdapter pointing to a temporary projects directory."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    return URLIntakeAdapter(projects_dir=projects_dir)


@pytest.fixture
def sample_video_path(tmp_path):
    """Generate a real 1-second test MP4 with synthetic audio via FFmpeg."""
    ensure_media_tools_on_path()
    video_file = tmp_path / "test_synth.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        str(video_file),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, f"FFmpeg synthetic video generation failed: {proc.stderr}"
    assert video_file.is_file() and video_file.stat().st_size > 0
    return video_file


# --- 1. Project ID Validation ---

def test_validate_project_id_valid(adapter):
    """Valid project IDs should pass without error."""
    adapter.validate_project_id("valid-project-id")
    adapter.validate_project_id("clip_factory_123")
    adapter.validate_project_id("PodcastEpisode1")


def test_validate_project_id_invalid(adapter):
    """Path traversal and special characters must be rejected."""
    invalid_ids = [
        "",
        "../traversal",
        "../../etc/passwd",
        "nested/path",
        "nested\\path",
        "project;cmd",
        "has spaces",
    ]
    for pid in invalid_ids:
        with pytest.raises(URLValidationError):
            adapter.validate_project_id(pid)


# --- 2. URL Scheme and Domain Validation ---

def test_validate_url_schemes(adapter):
    """Only http and https are allowed."""
    assert adapter.validate_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert adapter.validate_url("http://vimeo.com/123456789")

    invalid_schemes = [
        "file:///etc/passwd",
        "ftp://example.com/video.mp4",
        "data:text/html,<html>",
        "gopher://example.com",
    ]
    for u in invalid_schemes:
        with pytest.raises(URLValidationError, match="Unsupported URL scheme"):
            adapter.validate_url(u)


def test_validate_url_domains(adapter):
    """Only supported domains (YouTube, Vimeo) are accepted for MVP."""
    unsupported = [
        "https://evil.com/video.mp4",
        "https://dailymotion.com/video/x123",
        "https://attacker.org/test",
    ]
    for u in unsupported:
        with pytest.raises(URLValidationError, match="is not supported for MVP"):
            adapter.validate_url(u)


# --- 3. SSRF and Private Network Protection ---

def test_validate_url_ssrf_blocking(adapter):
    """Private, loopback, and link-local destinations must be blocked."""
    with patch("socket.getaddrinfo") as mock_dns:
        # Loopback IPv4
        mock_dns.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]
        with pytest.raises(URLValidationError, match="Blocked loopback"):
            adapter.validate_url("https://www.youtube.com/watch?v=123")

        # Private RFC 1918
        mock_dns.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.100", 0))]
        with pytest.raises(URLValidationError, match="Blocked private network"):
            adapter.validate_url("https://www.youtube.com/watch?v=123")

        # Link-local cloud metadata
        mock_dns.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]
        with pytest.raises(URLValidationError, match="Blocked link-local"):
            adapter.validate_url("https://www.youtube.com/watch?v=123")

        # Loopback IPv6
        mock_dns.return_value = [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 0, 0, 0))]
        with pytest.raises(URLValidationError, match="Blocked loopback"):
            adapter.validate_url("https://www.youtube.com/watch?v=123")


# --- 4. Disk Space Headroom Checking ---

def test_check_disk_headroom_sufficient(adapter, tmp_path):
    """Normal disk space passes cleanly."""
    adapter.check_disk_headroom(tmp_path, estimated_duration_seconds=60.0)


def test_check_disk_headroom_insufficient(adapter, tmp_path):
    """Insufficient free space raises DiskSpaceError."""
    with patch("shutil.disk_usage") as mock_usage:
        # Report only 100MB free
        mock_usage.return_value = (1_000_000_000, 900_000_000, 100 * 1024 * 1024)
        with pytest.raises(DiskSpaceError, match="Insufficient disk space"):
            adapter.check_disk_headroom(tmp_path, estimated_duration_seconds=3600.0)


# --- 5. Container Inspection and Remuxing ---

def test_ensure_valid_mp4(adapter, sample_video_path, tmp_path):
    """Test valid MP4 inspection and copy."""
    target_mp4 = tmp_path / "normalized.mp4"
    result_path = adapter.ensure_valid_mp4(sample_video_path, target_mp4)
    assert result_path.is_file()
    assert result_path.stat().st_size > 0

    probe = adapter.probe_media_file(result_path)
    assert any(s.get("codec_type") == "video" for s in probe.get("streams", []))


def test_ensure_valid_mp4_remux_from_mkv(adapter, sample_video_path, tmp_path):
    """Convert sample MP4 to MKV, then verify ensure_valid_mp4 explicitly remuxes to MP4."""
    mkv_path = tmp_path / "test.mkv"
    subprocess.run(["ffmpeg", "-y", "-i", str(sample_video_path), "-c", "copy", str(mkv_path)], check=True)
    assert mkv_path.is_file()

    target_mp4 = tmp_path / "remuxed.mp4"
    result = adapter.ensure_valid_mp4(mkv_path, target_mp4)
    assert result.is_file()
    probe = adapter.probe_media_file(result)
    fmt_name = probe.get("format", {}).get("format_name", "").lower()
    assert "mp4" in fmt_name or "mov" in fmt_name


# --- 6. Audio Fallback Extraction ---

def test_extract_audio_fallback(adapter, sample_video_path, tmp_path):
    """Test fallback extraction of 16kHz mono WAV from video."""
    target_wav = tmp_path / "extracted.wav"
    result = adapter.extract_audio_fallback(sample_video_path, target_wav)
    assert result.is_file()
    assert result.stat().st_size > 1024

    probe = adapter.probe_media_file(result)
    audio_stream = next((s for s in probe.get("streams", []) if s.get("codec_type") == "audio"), None)
    assert audio_stream is not None
    assert audio_stream.get("codec_name") == "pcm_s16le"
    assert audio_stream.get("sample_rate") == "16000"
    assert audio_stream.get("channels") == 1


# --- 7. Full Ingest Flow with Mocked Downloader and Real Media ---

def test_ingest_url_full_flow(adapter, sample_video_path, tmp_path):
    """End-to-end unit test: Mock downloader to supply real media, verify manifest & artifacts."""
    project_id = "test-clip-run"

    # Mock video_downloader tool execution
    mock_downloader = MagicMock()
    mock_downloader.execute.side_effect = [
        # Metadata pass
        ToolResult(
            success=True,
            data={"metadata": {"duration": 1.0, "title": "Test Synthetic Video"}},
        ),
        # Video download pass
        ToolResult(
            success=True,
            data={
                "video_path": str(sample_video_path),
                "audio_path": None,  # Simulate upstream missing audio to trigger fallback
                "metadata": {"duration": 1.0, "title": "Test Synthetic Video"},
            },
        ),
    ]

    # Mock transcript_fetcher
    mock_transcript_fetcher = MagicMock()
    mock_transcript_fetcher.execute.return_value = ToolResult(
        success=True,
        data={
            "transcript": [{"text": "Hello world", "start": 0.0, "duration": 1.0}],
            "full_text": "Hello world",
        },
    )

    with patch.object(adapter, "validate_url", return_value="https://www.youtube.com/watch?v=mock1234567"), \
         patch("lib.url_ingest.registry") as mock_registry:

        def get_tool(name):
            if name == "video_downloader":
                return mock_downloader
            if name == "transcript_fetcher":
                return mock_transcript_fetcher
            return None

        mock_registry.get.side_effect = get_tool
        mock_registry.ensure_discovered.return_value = None

        res = adapter.ingest_url("https://www.youtube.com/watch?v=mock1234567", project_id)

        assert res.success is True
        assert res.project_id == project_id
        assert Path(res.video_path).is_file()
        assert Path(res.video_path).name == "source_video.mp4"
        assert Path(res.audio_path).is_file()
        assert Path(res.audio_path).name == "source_audio.wav"
        assert res.has_native_captions is True
        assert Path(res.transcript_path).is_file()
        assert Path(res.manifest_path).is_file()

        # Check source_manifest.json contents
        with open(res.manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        assert manifest["project_id"] == project_id
        assert manifest["duration_seconds"] > 0
        assert manifest["has_native_captions"] is True
        assert manifest["video_codec"] == "h264"
        assert manifest["audio_codec"] == "pcm_s16le"


# --- 8. Handoff to lib/source_media_review.py ---

def test_handoff_to_source_media_review(adapter, sample_video_path, tmp_path):
    """Verify that an ingested video seamlessly passes into lib/source_media_review.py."""
    from lib.source_media_review import review_source_media

    project_id = "test-handoff-project"
    project_dir = adapter.projects_dir / project_id
    source_dir = project_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    dest_video = source_dir / "source_video.mp4"
    shutil.copy2(sample_video_path, dest_video)

    ingest_res = URLIngestResult(
        success=True,
        project_id=project_id,
        source_url="https://www.youtube.com/watch?v=mock1234567",
        video_path=str(dest_video),
        audio_path=str(source_dir / "source_audio.wav"),
    )

    review_art = adapter.review_ingested_media(ingest_res)
    assert review_art is not None
    assert "files" in review_art
    assert len(review_art["files"]) == 1

    file_info = review_art["files"][0]
    assert file_info["media_type"] == "video"
    assert Path(file_info["path"]).name == "source_video.mp4"
    assert file_info["technical_probe"]["duration_seconds"] > 0
