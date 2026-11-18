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
    instance = URLIntakeAdapter(projects_dir=projects_dir)
    instance._resolve_host = lambda host: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0))]
    return instance


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
    assert adapter.validate_url("https://vimeo.com/123456789")
    with pytest.raises(URLValidationError, match="HTTPS is required"):
        adapter.validate_url("http://vimeo.com/123456789")

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
    with patch.object(adapter, "_resolve_host") as mock_dns:
        # Loopback IPv4
        mock_dns.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]
        with pytest.raises(URLValidationError, match="Blocked loopback"):
            adapter.validate_url("https://www.youtube.com/watch?v=123")


def test_validate_url_dns_failure_is_closed(adapter):
    with patch.object(adapter, "_resolve_host", side_effect=socket.gaierror("offline")):
        with pytest.raises(URLValidationError, match="Could not resolve"):
            adapter.validate_url("https://www.youtube.com/watch?v=123")


def test_transactional_commit_rolls_back_and_removes_stale_transcript(tmp_path):
    from lib.url_ingest import URLIntakeAdapter
    video = tmp_path / "source_video.mp4"
    transcript = tmp_path / "transcript.json"
    video.write_text("old")
    transcript.write_text("stale")
    new_video = tmp_path / "new.mp4"
    new_video.write_text("new")
    new_audio = tmp_path / "new.wav"
    new_audio.write_text("audio")
    real_replace = __import__("os").replace
    calls = {"n": 0}
    def fail_midway(src, dst):
        calls["n"] += 1
        if calls["n"] == 4:
            raise OSError("simulated locked file")
        return real_replace(src, dst)
    with patch("lib.url_ingest.os.replace", side_effect=fail_midway):
        with pytest.raises(OSError):
            URLIntakeAdapter._commit_bundle({video: new_video, tmp_path / "source_audio.wav": new_audio, transcript: None})
    assert video.read_text() == "old"
    assert transcript.read_text() == "stale"
    new_video.write_text("new")
    new_audio.write_text("audio")
    URLIntakeAdapter._commit_bundle({video: new_video, tmp_path / "source_audio.wav": new_audio, transcript: None})
    assert video.read_text() == "new"
    assert not transcript.exists()


def test_transient_download_retry_is_bounded(adapter):
    assert adapter._transient_error("connection reset")
    assert not adapter._transient_error("unsupported format")


@pytest.mark.parametrize("duration", [0, -1, 9999])
def test_post_probe_duration_validation_and_staging_cleanup(adapter, sample_video_path, duration):
    tool = MagicMock()
    tool.execute.side_effect = [
        ToolResult(success=True, data={"metadata": {"duration": 1}}),
        ToolResult(success=True, data={"video_path": str(sample_video_path), "audio_path": None}),
    ]
    with patch.object(adapter, "validate_url", return_value="https://www.youtube.com/watch?v=mock1234567"), patch("lib.url_ingest.registry") as reg:
        reg.get.side_effect = lambda name: tool if name == "video_downloader" else None
        reg.ensure_discovered.return_value = None
        adapter.extract_audio_fallback = lambda src, dst: (dst.write_bytes(b"audio") or dst)
        original_probe = adapter.probe_media_file
        def probe(path):
            if Path(path).name == "source_audio.wav":
                return {"streams": [{"codec_type":"audio", "codec_name":"pcm_s16le", "sample_rate":"16000", "channels":1}]}
            return {"format":{"duration":str(duration)}, "streams":[{"codec_type":"video", "codec_name":"h264", "width":1,"height":1}]}
        adapter.ensure_valid_mp4 = lambda src, dst: (shutil.copy2(src, dst) and dst)
        adapter.probe_media_file = probe
        result = adapter.ingest_url("https://www.youtube.com/watch?v=mock1234567", "duration-check")
    assert not result.success
    assert not list((adapter.projects_dir / "duration-check" / "source").glob(".staging_*"))


def test_url_intake_tool_discovery_and_pipeline_propagation(adapter, sample_video_path):
    from tools.analysis.url_intake import URLIntake
    from tools.tool_registry import ToolRegistry
    tool = URLIntake()
    assert tool.name == "url_intake"
    assert tool.get_status() is not None
    assert ToolRegistry is not None
    adapter.pipeline_type = "podcast-repurpose"
    assert adapter.pipeline_type == "podcast-repurpose"


def test_transcript_fetcher_prefers_manual_language_and_respects_auto_flag(monkeypatch):
    import sys
    from types import SimpleNamespace
    from tools.analysis.transcript_fetcher import TranscriptFetcher
    class Track:
        def __init__(self, code, generated):
            self.language_code, self.is_generated, self.language = code, generated, code
        def fetch(self):
            return SimpleNamespace(snippets=[SimpleNamespace(text=self.language_code, start=0, duration=1)], is_generated=self.is_generated, language=self.language_code)
    tracks = [Track("en", True), Track("hi", False)]
    class API:
        def list(self, _video_id): return tracks
    monkeypatch.setitem(sys.modules, "youtube_transcript_api", SimpleNamespace(YouTubeTranscriptApi=API))
    tool = TranscriptFetcher()
    preferred = tool.execute({"url_or_video_id":"abcdefghijk", "languages":["en", "hi"]})
    assert preferred.success and preferred.data["language"] == "hi" and not preferred.data["is_auto_generated"]
    tracks[:] = [Track("en", True)]
    excluded = tool.execute({"url_or_video_id":"abcdefghijk", "languages":["en"], "include_auto_generated":False})
    assert not excluded.success


def test_video_downloader_allowed_extractors_are_opt_in(monkeypatch, tmp_path):
    import sys
    from types import SimpleNamespace
    from tools.analysis.video_downloader import VideoDownloader
    opts_seen = []
    class YDL:
        def __init__(self, opts): opts_seen.append(opts)
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def extract_info(self, *_args, **_kwargs): return {"duration":10}
        def download(self, _urls): return None
    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=YDL))
    downloader = VideoDownloader()
    downloader._extract_metadata("https://example.com/video")
    downloader._extract_metadata("https://youtube.com/watch?v=abcdefghijk", ["youtube", "vimeo"])
    assert "allowed_extractors" not in opts_seen[0]
    assert opts_seen[1]["allowed_extractors"] == ["youtube", "vimeo"]
    downloader._download_video("https://instagram.com/reel/x", tmp_path, "720p")
    assert "allowed_extractors" not in opts_seen[-1]
    downloader._download_video("https://youtube.com/watch?v=abcdefghijk", tmp_path, "720p", ["youtube", "vimeo"])
    assert opts_seen[-1]["allowed_extractors"] == ["youtube", "vimeo"]


def test_video_downloader_rejects_unknown_duration_and_propagates_metadata_errors(monkeypatch, tmp_path):
    import sys
    from types import SimpleNamespace
    from tools.analysis.video_downloader import VideoDownloader

    download_calls = []

    class YDL:
        info = {"duration": 0}
        error = None
        def __init__(self, _opts): pass
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def extract_info(self, *_args, **_kwargs):
            if self.error:
                raise RuntimeError(self.error)
            return self.info
        def download(self, _urls): download_calls.append(True)

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=YDL))
    downloader = VideoDownloader()
    inputs = {"url": "https://youtube.com/watch?v=abcdefghijk", "format": "video",
              "output_dir": str(tmp_path)}
    unknown = downloader.execute(inputs)
    assert not unknown.success and "duration is unknown" in unknown.error
    assert download_calls == []

    YDL.error = "extractor timed out"
    extraction_error = downloader.execute({**inputs, "format": "metadata_only"})
    assert not extraction_error.success and "extractor timed out" in extraction_error.error


def test_video_downloader_size_limit_is_forwarded_and_postchecked(monkeypatch, tmp_path):
    import sys
    from types import SimpleNamespace
    from tools.analysis.video_downloader import VideoDownloader

    seen = []

    class YDL:
        def __init__(self, options):
            self.options = options
            seen.append(options)
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def extract_info(self, *_args, **_kwargs): return {"duration": 1}
        def download(self, _urls):
            Path(self.options["outtmpl"].replace("%(ext)s", "mp4")).write_bytes(b"oversized")

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=YDL))
    result = VideoDownloader().execute({
        "url": "https://youtube.com/watch?v=abcdefghijk", "format": "video",
        "output_dir": str(tmp_path), "max_file_size_bytes": 4,
    })
    assert not result.success and "exceeds max_file_size_bytes=4" in result.error
    assert seen[-1]["max_filesize"] == 4 and seen[-1]["noplaylist"] is True
    assert not list(tmp_path.glob("reference_video.*"))


def _mock_intake_registry(adapter, mock_downloader):
    def get_tool(name):
        return mock_downloader if name == "video_downloader" else None
    return patch("lib.url_ingest.registry.get", side_effect=get_tool), patch("lib.url_ingest.registry.ensure_discovered")


def test_ingest_url_non_wav_audio_triggers_pcm_fallback(adapter, sample_video_path, tmp_path):
    compressed = tmp_path / "compressed.m4a"
    subprocess.run(["ffmpeg", "-y", "-i", str(sample_video_path), "-vn", "-c:a", "aac", str(compressed)], check=True, capture_output=True)
    tool = MagicMock()
    tool.execute.side_effect = [ToolResult(True, {"metadata":{"duration":1}}), ToolResult(True, {"video_path":str(sample_video_path), "audio_path":str(compressed)})]
    registry_patch, discover_patch = _mock_intake_registry(adapter, tool)
    with patch.object(adapter, "validate_url", return_value="https://www.youtube.com/watch?v=mock1234567"), registry_patch, discover_patch:
        result = adapter.ingest_url("https://youtube.com/watch?v=mock1234567", "nonwav", extract_transcript=False)
    assert result.success
    stream = next(s for s in adapter.probe_media_file(Path(result.audio_path))["streams"] if s["codec_type"] == "audio")
    assert stream["codec_name"] == "pcm_s16le" and stream["sample_rate"] == "16000" and stream["channels"] == 1


def test_ingest_url_accepts_podcast_longer_than_downloader_default(adapter, sample_video_path):
    url = "https://youtube.com/watch?v=mock1234567"
    tool = MagicMock()
    tool.execute.side_effect = [
        ToolResult(True, {"metadata": {"duration": 1800}}),
        ToolResult(True, {"video_path": str(sample_video_path), "audio_path": None}),
    ]
    registry_patch, discover_patch = _mock_intake_registry(adapter, tool)
    actual_probe = adapter.probe_media_file

    def probe(path):
        result = actual_probe(path)
        if Path(path).name == "source_video.mp4":
            result["format"]["duration"] = "1800"
        return result

    adapter.probe_media_file = probe
    adapter.ensure_valid_mp4 = lambda src, dst: (shutil.copy2(src, dst) and dst)
    with patch.object(adapter, "validate_url", return_value=url), registry_patch, discover_patch:
        result = adapter.ingest_url(url, "long-podcast", max_duration_seconds=3600, extract_transcript=False)
    assert result.success, result.error
    assert result.duration_seconds == 1800
    preflight_inputs = tool.execute.call_args_list[0].args[0]
    assert preflight_inputs["format"] == "metadata_only"
    assert preflight_inputs["max_duration_seconds"] == 3600


def test_ingest_url_bounded_retries(adapter, sample_video_path, monkeypatch):
    monkeypatch.setattr("lib.url_ingest.time.sleep", lambda _: None)
    url = "https://youtube.com/watch?v=mock1234567"
    for failures, expected_calls, should_succeed in [
        (["HTTP Error 503"], 2, True), (["connection reset"] * 3, 3, False), (["private video"], 1, False),
    ]:
        tool = MagicMock()
        calls = {"download":0}
        def execute(inputs):
            if inputs["format"] == "metadata_only": return ToolResult(True, {"metadata":{"duration":1}})
            calls["download"] += 1
            if calls["download"] <= len(failures): return ToolResult(False, error=failures[calls["download"]-1])
            return ToolResult(True, {"video_path":str(sample_video_path), "audio_path":None})
        tool.execute.side_effect = execute
        registry_patch, discover_patch = _mock_intake_registry(adapter, tool)
        with patch.object(adapter, "validate_url", return_value=url), registry_patch, discover_patch:
            result = adapter.ingest_url(url, f"retry-{len(failures)}-{expected_calls}", extract_transcript=False)
        assert result.success is should_succeed and calls["download"] == expected_calls


def test_ingest_url_non_h264_creates_proxy_and_url_intake_artifacts(adapter, tmp_path, monkeypatch):
    from tools.analysis.url_intake import URLIntake
    source = tmp_path / "mpeg4.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=24", "-f", "lavfi", "-i", "sine=duration=1", "-c:v", "mpeg4", "-c:a", "aac", str(source)], check=True, capture_output=True)
    tool = MagicMock()
    tool.execute.side_effect = [ToolResult(True, {"metadata":{"duration":1}}), ToolResult(True, {"video_path":str(source), "audio_path":None})]
    registry_patch, discover_patch = _mock_intake_registry(adapter, tool)
    adapter.pipeline_type = "podcast-repurpose"
    monkeypatch.setattr("tools.analysis.url_intake.URLIntakeAdapter", lambda pipeline_type: adapter)
    with patch.object(adapter, "validate_url", return_value="https://youtube.com/watch?v=mock1234567"), registry_patch, discover_patch:
        output = URLIntake().execute({"url":"https://youtube.com/watch?v=mock1234567", "project_id":"proxy-test", "pipeline_type":"podcast-repurpose"})
    assert output.success
    master = Path(output.data["video_path"])
    proxy = master.with_name("source_video_h264.mp4")
    assert master.is_file() and proxy.is_file()
    original = next(s for s in adapter.probe_media_file(master)["streams"] if s["codec_type"] == "video")
    encoded = next(s for s in adapter.probe_media_file(proxy)["streams"] if s["codec_type"] == "video")
    assert original["codec_name"] == "mpeg4"
    assert encoded["codec_name"] == "h264" and encoded["pix_fmt"] == "yuv420p"
    manifest = json.loads(Path(output.data["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["pipeline_type"] == "podcast-repurpose"
    assert manifest["master_video_path"] and manifest["proxy_video_path"] == str(proxy)
    assert output.data["proxy_video_path"] == str(proxy) and str(proxy) in output.artifacts


def test_url_intake_execute_returns_artifacts_proxy_and_clean_error(monkeypatch, tmp_path):
    import json
    from tools.analysis.url_intake import URLIntake
    from lib.url_ingest import URLIngestResult, URLValidationError
    source = tmp_path / "source"
    source.mkdir()
    video, audio, manifest = source / "v.mp4", source / "a.wav", source / "source_manifest.json"
    video.write_text("video"); audio.write_text("audio")
    manifest.write_text(json.dumps({"pipeline_type":"podcast-repurpose", "proxy_video_path":None}))
    result = URLIngestResult(True, "p", "https://youtube.com", str(video), str(audio), manifest_path=str(manifest))
    class Adapter:
        def __init__(self, pipeline_type): assert pipeline_type == "podcast-repurpose"
        def ingest_url(self, *_args, **_kwargs): return result
    monkeypatch.setattr("tools.analysis.url_intake.URLIntakeAdapter", Adapter)
    output = URLIntake().execute({"url":"https://youtube.com", "project_id":"p", "pipeline_type":"podcast-repurpose"})
    assert output.success and output.data["proxy_video_path"] is None
    assert set(output.artifacts) == {str(video), str(audio), str(manifest)}
    class BadAdapter(Adapter):
        def __init__(self, pipeline_type): pass
        def ingest_url(self, *_args, **_kwargs): raise URLValidationError("bad url")
    monkeypatch.setattr("tools.analysis.url_intake.URLIntakeAdapter", BadAdapter)
    failed = URLIntake().execute({"url":"http://bad", "project_id":"p", "pipeline_type":"clip-factory"})
    assert not failed.success and failed.error == "bad url"

def test_validate_url_private_and_link_local_blocked(adapter):
    for address, expected in [("192.168.1.100", "Blocked private network"), ("169.254.169.254", "Blocked link-local"), ("::1", "Blocked loopback")]:
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        entry = (family, socket.SOCK_STREAM, 6, "", (address, 0, 0, 0) if family == socket.AF_INET6 else (address, 0))
        with patch.object(adapter, "_resolve_host", return_value=[entry]):
            with pytest.raises(URLValidationError, match=expected):
                adapter.validate_url("https://www.youtube.com/watch?v=123")


def test_validate_url_unspecified_and_ipv4_mapped_addresses_blocked(adapter):
    for address in ("0.0.0.0", "::ffff:127.0.0.1"):
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        sockaddr = (address, 0, 0, 0) if family == socket.AF_INET6 else (address, 0)
        entry = (family, socket.SOCK_STREAM, 6, "", sockaddr)
        with patch.object(adapter, "_resolve_host", return_value=[entry]):
            with pytest.raises(URLValidationError, match="Blocked"):
                adapter.validate_url("https://www.youtube.com/watch?v=123")


def test_local_media_intake_copies_transcript_and_emits_manifest(adapter, sample_video_path):
    sidecar = sample_video_path.with_suffix(".srt")
    sidecar.write_text("1\n00:00:00,000 --> 00:00:00,800\nLocal transcript\n", encoding="utf-8")
    result = adapter.ingest_local_file(sample_video_path, "local-intake", transcript_path=sidecar)
    assert result.success
    assert Path(result.video_path).is_file() and Path(result.audio_path).is_file()
    assert Path(result.transcript_path).read_text(encoding="utf-8").startswith("1\n")
    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert manifest["pipeline_type"] == adapter.pipeline_type
    assert manifest["has_native_captions"] is True
    assert manifest["master_video_path"] == result.video_path
    assert manifest["proxy_video_path"] is None


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


# --- 9. Phase 1 Preflight Duration/Quality Gates & SSRF Guard ---

def test_ingest_url_enforces_min_duration_and_strict_quality_gate(adapter):
    url = "https://www.youtube.com/watch?v=mock1234567"

    # Too short when min_duration_seconds is enabled
    short_tool = MagicMock()
    short_tool.execute.return_value = ToolResult(
        True, {"metadata": {"duration": 25, "max_available_height": 1080}}
    )
    reg_p, disc_p = _mock_intake_registry(adapter, short_tool)
    with patch.object(adapter, "validate_url", return_value=url), reg_p, disc_p:
        res = adapter.ingest_url(url, "too-short", min_duration_seconds=60, extract_transcript=False)
    assert not res.success
    assert "min_duration_seconds" in (res.error or "")

    # Low resolution rejected when strict_quality_gate=True
    lowres_tool = MagicMock()
    lowres_tool.execute.return_value = ToolResult(
        True, {"metadata": {"duration": 180, "max_available_height": 360}}
    )
    reg_p2, disc_p2 = _mock_intake_registry(adapter, lowres_tool)
    with patch.object(adapter, "validate_url", return_value=url), reg_p2, disc_p2:
        res2 = adapter.ingest_url(
            url,
            "low-res",
            min_quality_height=480,
            strict_quality_gate=True,
            extract_transcript=False,
        )
    assert not res2.success
    assert "min_quality_height" in (res2.error or "")


def test_video_downloader_extract_metadata_blocks_private_format_urls_and_reports_max_height(monkeypatch):
    import sys
    from types import SimpleNamespace
    from tools.analysis.video_downloader import VideoDownloader

    opts_seen = []

    class YDLGood:
        def __init__(self, opts):
            opts_seen.append(opts)
        def __enter__(self): return self
        def __exit__(self, *_a): return False
        def extract_info(self, *_a, **_kw):
            return {
                "title": "Podcast",
                "duration": 900,
                "formats": [
                    {"height": 480, "url": "https://rr1.googlevideo.com/480"},
                    {"height": 1080, "url": "https://rr2.googlevideo.com/1080"},
                ],
            }

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=YDLGood))
    dl = VideoDownloader()
    meta = dl._extract_metadata("https://www.youtube.com/watch?v=abcdefghijk")
    assert meta["max_available_height"] == 1080
    assert opts_seen[-1]["noplaylist"] is True

    class YDLPoisoned(YDLGood):
        def extract_info(self, *_a, **_kw):
            return {
                "title": "Evil",
                "duration": 120,
                "formats": [{"height": 720, "url": "http://169.254.169.254/latest/meta-data/"}],
            }

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=YDLPoisoned))
    bad_meta = dl._extract_metadata("https://www.youtube.com/watch?v=abcdefghijk")
    assert "error" in bad_meta and "non-public" in bad_meta["error"]

