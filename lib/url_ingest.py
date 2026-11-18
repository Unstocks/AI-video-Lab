"""URL Intake Adapter for OpenMontage.

Acquires source media from supported video URLs (YouTube, Vimeo) into the
canonical project source directory (`projects/<project-id>/source/`),
validating protocols, blocking private/loopback SSRF, checking disk headroom,
remuxing non-MP4 containers explicitly, enforcing audio verification with
FFmpeg fallback, fetching native transcripts, and emitting a validated
source_manifest.json.

Preserves 100% of upstream OpenMontage architecture. Does not modify
lib/source_media_review.py or tools/base_tool.py.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import math
import os
import re
import shutil
import socket
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from tools.tool_registry import registry

logger = logging.getLogger(__name__)

# Supported domain patterns for MVP
_SUPPORTED_DOMAINS = frozenset({
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "vimeo.com",
    "www.vimeo.com",
    "player.vimeo.com",
})

# Project ID safe naming regex (prevents path traversal)
_SAFE_PROJECT_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]+$")


def ensure_media_tools_on_path() -> None:
    """Ensure ffmpeg and ffprobe binaries are resolvable on system PATH.

    Checks workspace runtime tools and venv scripts directories if system PATH
    does not already resolve them.
    """
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return

    workspace_root = Path(__file__).resolve().parent.parent
    configured_bin = os.environ.get("FFMPEG_BIN_DIR")
    candidate_dirs = ([Path(configured_bin).expanduser()] if configured_bin else []) + [
        workspace_root / ".runtime" / "tools" / "bin",
        workspace_root / ".venv" / "Scripts",
    ]

    for c_dir in candidate_dirs:
        ffmpeg_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
        ffprobe_name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
        if (c_dir / ffmpeg_name).is_file() and (c_dir / ffprobe_name).is_file():
            os.environ["PATH"] = str(c_dir) + os.pathsep + os.environ.get("PATH", "")
            logger.info("Prepended media tools to PATH: %s", c_dir)
            break


# Ensure media tools are present on PATH as soon as module is imported
ensure_media_tools_on_path()


class URLValidationError(ValueError):
    """Raised when a URL is invalid, unsupported, or poses a security risk."""


class DiskSpaceError(RuntimeError):
    """Raised when target storage has insufficient capacity."""


class MediaIngestionError(RuntimeError):
    """Raised when media download, remuxing, or validation fails."""


@dataclass
class URLIngestResult:
    """Result of URL ingestion and source artifact materialization."""

    success: bool
    project_id: str
    source_url: str
    video_path: Optional[str] = None
    audio_path: Optional[str] = None
    transcript_path: Optional[str] = None
    manifest_path: Optional[str] = None
    has_native_captions: bool = False
    duration_seconds: float = 0.0
    resolution: tuple[int, int] = (0, 0)
    fps: float = 0.0
    video_codec: str = ""
    audio_codec: str = ""
    file_size_bytes: int = 0
    error: Optional[str] = None
    acquired_at: str = ""


class URLIntakeAdapter:
    """Adapter for ingesting remote video URLs into OpenMontage projects."""

    def __init__(self, projects_dir: Optional[Path] = None, *, pipeline_type: str = "clip-factory") -> None:
        ensure_media_tools_on_path()
        self.workspace_root = Path(__file__).resolve().parent.parent
        self.projects_dir = projects_dir or (self.workspace_root / "projects")
        self.pipeline_type = pipeline_type

    @staticmethod
    def _commit_bundle(files: dict[Path, Optional[Path]]) -> None:
        backup_dir = next(iter(files)).parent / f".backup_{uuid.uuid4().hex}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backups: dict[Path, Path] = {}
        installed: list[Path] = []
        try:
            for i, target in enumerate(files):
                if target.exists():
                    backup = backup_dir / str(i)
                    os.replace(target, backup)
                    backups[target] = backup
            for target, staged in files.items():
                if staged is not None:
                    os.replace(staged, target)
                    installed.append(target)
        except Exception:
            for target in reversed(installed):
                target.unlink(missing_ok=True)
            for target, backup in backups.items():
                if backup.exists():
                    os.replace(backup, target)
            raise
        finally:
            shutil.rmtree(backup_dir, ignore_errors=True)

    @staticmethod
    def _transient_error(error: Any) -> bool:
        value = str(error).lower()
        return any(x in value for x in ("timeout", "temporarily unavailable", "connection reset", "connection aborted", "http error 5"))

    def validate_project_id(self, project_id: str) -> None:
        """Validate project identifier to prevent path traversal."""
        if not project_id or not _SAFE_PROJECT_ID_REGEX.match(project_id):
            raise URLValidationError(
                f"Invalid project_id '{project_id}'. Must be alphanumeric with hyphens/underscores, "
                f"no path separators or traversal."
            )

    def validate_url(self, url: str) -> str:
        """Validate URL scheme, domain whitelist, and block private/loopback SSRF."""
        if not url or not isinstance(url, str):
            raise URLValidationError("URL must be a non-empty string.")

        parsed = urlparse(url.strip())
        if parsed.scheme.lower() != "https":
            raise URLValidationError(
                f"Unsupported URL scheme '{parsed.scheme}'. HTTPS is required."
            )

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            raise URLValidationError(f"Invalid URL: missing hostname in '{url}'.")

        # Domain whitelist check
        is_supported = hostname in _SUPPORTED_DOMAINS or any(
            hostname.endswith("." + d) for d in ("youtube.com", "vimeo.com")
        )
        if not is_supported:
            raise URLValidationError(
                f"Domain '{hostname}' is not supported for MVP. Supported domains: YouTube, Vimeo."
            )

        # Anti-SSRF: Resolve IP addresses and block private/loopback/link-local
        try:
            addr_info = self._resolve_host(hostname)
            if not addr_info:
                raise URLValidationError(f"DNS returned no addresses for approved host '{hostname}'.")
            for item in addr_info:
                ip_str = item[4][0]
                ip_obj = ipaddress.ip_address(ip_str)
                mapped = getattr(ip_obj, "ipv4_mapped", None)
                if mapped is not None:
                    ip_obj = mapped
                if ip_obj.is_unspecified:
                    reason = "unspecified"
                elif ip_obj.is_loopback:
                    reason = "loopback"
                elif ip_obj.is_link_local:
                    reason = "link-local"
                elif ip_obj.is_private:
                    reason = "private network"
                elif ip_obj.is_reserved or ip_obj.is_multicast or not ip_obj.is_global:
                    reason = "non-global"
                else:
                    reason = ""
                if reason:
                    raise URLValidationError(f"Blocked {reason} destination: {ip_str}")
        except URLValidationError:
            raise
        except Exception as exc:
            try:
                ip_obj = ipaddress.ip_address(hostname)
            except ValueError:
                raise URLValidationError(f"Could not resolve approved host '{hostname}'.") from exc
            mapped = getattr(ip_obj, "ipv4_mapped", None)
            if mapped is not None:
                ip_obj = mapped
            if ip_obj.is_unspecified or not ip_obj.is_global:
                raise URLValidationError(f"Blocked non-global destination IP: {hostname}") from exc

        return url.strip()

    @staticmethod
    def _resolve_host(hostname: str) -> list:
        """DNS seam used for deterministic offline validation tests."""
        return socket.getaddrinfo(hostname, None)

    def check_disk_headroom(
        self, output_dir: Path, estimated_duration_seconds: float = 600.0
    ) -> None:
        """Verify destination drive has sufficient free disk space."""
        # Heuristic: 4 Mbps average bitrate -> ~0.5 MB/sec
        estimated_bytes = int(estimated_duration_seconds * 500_000)
        # Formula: (Estimated Size * 2.5) + 1.0 GB cushion
        required_free_bytes = int(estimated_bytes * 2.5) + 1_073_741_824

        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            usage = shutil.disk_usage(output_dir)
            free_bytes = getattr(usage, "free", usage[2] if isinstance(usage, tuple) and len(usage) > 2 else 0)
            if free_bytes < required_free_bytes:
                free_mb = free_bytes / (1024 * 1024)
                req_mb = required_free_bytes / (1024 * 1024)
                raise DiskSpaceError(
                    f"Insufficient disk space on {output_dir.drive or output_dir}. "
                    f"Available: {free_mb:.1f} MB, Required: {req_mb:.1f} MB."
                )
        except OSError as e:
            logger.warning("Could not check disk usage on %s: %s", output_dir, e)

    def probe_media_file(self, file_path: Path) -> dict[str, Any]:
        """Inspect media file format and streams via ffprobe."""
        ensure_media_tools_on_path()
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(file_path),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                raise MediaIngestionError(f"ffprobe failed: {proc.stderr}")
            return json.loads(proc.stdout)
        except Exception as e:
            raise MediaIngestionError(f"Failed to probe media file {file_path}: {e}") from e

    def ensure_valid_mp4(self, source_file: Path, target_mp4: Path) -> Path:
        """Ensure media is a compliant MP4 container, remuxing if necessary."""
        ensure_media_tools_on_path()
        probe = self.probe_media_file(source_file)
        fmt = probe.get("format", {})
        fmt_name = fmt.get("format_name", "").lower()
        streams = probe.get("streams", [])

        has_video = any(s.get("codec_type") == "video" for s in streams)
        if not has_video:
            raise MediaIngestionError(f"File {source_file} contains no valid video stream.")

        # Check if already a clean MP4/MOV container
        is_mp4_container = any(k in fmt_name for k in ("mp4", "mov", "m4a"))
        if is_mp4_container and source_file.suffix.lower() == ".mp4":
            if source_file.resolve() != target_mp4.resolve():
                shutil.copy2(source_file, target_mp4)
            return target_mp4

        logger.info("Remuxing %s (%s) to compliant MP4 container %s", source_file.name, fmt_name, target_mp4.name)

        # Attempt 1: Fast stream-copy remux
        remux_cmd = [
            "ffmpeg", "-y",
            "-i", str(source_file),
            "-c", "copy",
            "-movflags", "+faststart",
            str(target_mp4),
        ]
        proc = subprocess.run(remux_cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode == 0 and target_mp4.is_file() and target_mp4.stat().st_size > 1024:
            remux_probe = self.probe_media_file(target_mp4)
            if any(s.get("codec_type") == "video" for s in remux_probe.get("streams", [])):
                return target_mp4

        # Attempt 2: Re-encode video to H.264 / AAC if stream-copy failed (e.g. VP9/Opus webm)
        logger.info("Stream copy failed; transcoding %s to H.264/AAC MP4", source_file.name)
        transcode_cmd = [
            "ffmpeg", "-y",
            "-i", str(source_file),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(target_mp4),
        ]
        proc2 = subprocess.run(transcode_cmd, capture_output=True, text=True, timeout=300)
        if proc2.returncode != 0 or not target_mp4.is_file() or target_mp4.stat().st_size <= 1024:
            raise MediaIngestionError(f"Transcoding to MP4 failed: {proc2.stderr}")

        return target_mp4

    def extract_audio_fallback(self, video_file: Path, target_audio_wav: Path) -> Path:
        """Extract clean 16kHz mono WAV audio from video using FFmpeg."""
        ensure_media_tools_on_path()
        logger.info("Extracting audio from %s to %s", video_file.name, target_audio_wav.name)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_file),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(target_audio_wav),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0 or not target_audio_wav.is_file() or target_audio_wav.stat().st_size <= 1024:
            raise MediaIngestionError(f"FFmpeg audio extraction failed: {proc.stderr}")

        audio_probe = self.probe_media_file(target_audio_wav)
        has_audio = any(s.get("codec_type") == "audio" for s in audio_probe.get("streams", []))
        if not has_audio:
            raise MediaIngestionError(f"Extracted audio file {target_audio_wav} contains no audio stream.")

        return target_audio_wav

    def ingest_url(
        self,
        url: str,
        project_id: str,
        *,
        max_duration_seconds: int = 3600,
        max_file_size_bytes: int = 2 * 1024**3,
        preferred_quality: str = "720p",
        extract_transcript: bool = True,
        caption_languages: Optional[list[str]] = None,
    ) -> URLIngestResult:
        """Acquire video URL into project source directory with complete validation."""
        self.validate_project_id(project_id)
        validated_url = self.validate_url(url)

        registry.ensure_discovered()
        video_downloader = registry.get("video_downloader")
        if not video_downloader:
            return URLIngestResult(
                success=False,
                project_id=project_id,
                source_url=validated_url,
                error="video_downloader tool is not registered in ToolRegistry.",
            )

        project_dir = self.projects_dir / project_id
        source_dir = project_dir / "source"
        staging_dir = source_dir / f".staging_{uuid.uuid4().hex[:8]}"
        staging_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 1. Preflight Metadata Inspection
            meta_res = video_downloader.execute({
                "url": validated_url,
                "output_dir": str(staging_dir),
                "format": "metadata_only",
                "max_duration_seconds": max_duration_seconds,
                "allowed_extractors": ["youtube", "vimeo"],
            })
            metadata = meta_res.data.get("metadata", {}) if meta_res.success else {}
            if not meta_res.success:
                raise MediaIngestionError(meta_res.error or metadata.get("error") or "Metadata extraction failed.")
            if metadata.get("error"):
                raise MediaIngestionError(str(metadata["error"]))

            duration = float(metadata.get("duration") or 0.0)
            if duration <= 0 or duration > max_duration_seconds:
                return URLIngestResult(
                    success=False,
                    project_id=project_id,
                    source_url=validated_url,
                    error=f"Video metadata duration ({duration}s) is unknown or exceeds max limit ({max_duration_seconds}s).",
                )

            # 2. Check Disk Space Headroom
            self.check_disk_headroom(source_dir, estimated_duration_seconds=duration or 600.0)

            # 3. Download Source Media via video_downloader
            dl_inputs = {
                "url": validated_url,
                "output_dir": str(staging_dir),
                "format": "video",
                "max_resolution": preferred_quality,
                "max_duration_seconds": max_duration_seconds,
                "max_file_size_bytes": max_file_size_bytes,
                "allowed_extractors": ["youtube", "vimeo"],
            }
            for attempt in range(3):
                dl_res = video_downloader.execute(dl_inputs)
                if dl_res.success or attempt == 2 or not self._transient_error(dl_res.error):
                    break
                time.sleep(0.25 * (2 ** attempt))
            if not dl_res.success:
                return URLIngestResult(
                    success=False,
                    project_id=project_id,
                    source_url=validated_url,
                    error=f"Download failed: {dl_res.error}",
                )

            raw_video_path = dl_res.data.get("video_path")
            if not raw_video_path or not Path(raw_video_path).is_file():
                return URLIngestResult(
                    success=False,
                    project_id=project_id,
                    source_url=validated_url,
                    error="Download succeeded but no video file was produced.",
                )
            if Path(raw_video_path).stat().st_size > max_file_size_bytes:
                raise MediaIngestionError(f"Downloaded video exceeds max_file_size_bytes={max_file_size_bytes}.")

            # 4. Normalize & Remux Video to standard MP4
            staging_video_mp4 = staging_dir / "source_video.mp4"
            self.ensure_valid_mp4(Path(raw_video_path), staging_video_mp4)

            # 5. Verify & Extract Audio
            staging_audio_wav = staging_dir / "source_audio.wav"
            raw_audio_path = dl_res.data.get("audio_path")
            audio_valid = False
            if raw_audio_path and Path(raw_audio_path).is_file() and Path(raw_audio_path).stat().st_size > 1024:
                try:
                    probe = self.probe_media_file(Path(raw_audio_path))
                    stream = next((s for s in probe.get("streams", []) if s.get("codec_type") == "audio"), {})
                    if (stream.get("codec_name") == "pcm_s16le" and int(stream.get("sample_rate") or 0) == 16000
                            and int(stream.get("channels") or 0) == 1 and Path(raw_audio_path).suffix.lower() == ".wav"):
                        shutil.copy2(raw_audio_path, staging_audio_wav)
                        audio_valid = True
                except Exception:
                    audio_valid = False

            if not audio_valid:
                self.extract_audio_fallback(staging_video_mp4, staging_audio_wav)

            # 6. Extract Native Captions (if available)
            staging_transcript = staging_dir / "transcript.json"
            has_native_captions = False
            if extract_transcript:
                transcript_fetcher = registry.get("transcript_fetcher")
                if transcript_fetcher:
                    try:
                        tf_res = transcript_fetcher.execute({
                            "url_or_video_id": validated_url,
                            "languages": caption_languages or ["en", "hi"],
                        })
                        if tf_res.success and tf_res.data.get("transcript"):
                            with open(staging_transcript, "w", encoding="utf-8") as f:
                                json.dump(tf_res.data, f, indent=2)
                            has_native_captions = True
                    except Exception as e:
                        logger.warning("Transcript fetching failed: %s", e)

            # yt-dlp performs its own redirects and socket resolution. This
            # application preflight blocks known non-global DNS answers but
            # cannot bind later connections to those answers; run remote intake
            # inside an OS-level network sandbox for adversarial sources.

            # 7. Extract Final Technical Metadata via FFprobe
            video_probe = self.probe_media_file(staging_video_mp4)
            audio_probe = self.probe_media_file(staging_audio_wav)

            fmt_data = video_probe.get("format", {})
            v_streams = video_probe.get("streams", [])
            a_streams = audio_probe.get("streams", [])

            v_stream = next((s for s in v_streams if s.get("codec_type") == "video"), {})
            a_stream = next((s for s in a_streams if s.get("codec_type") == "audio"), {})

            def _parse_fps(rate_str: str) -> float:
                if "/" in rate_str:
                    num, den = rate_str.split("/", 1)
                    try:
                        return round(float(num) / float(den), 2)
                    except ZeroDivisionError:
                        return 0.0
                try:
                    return float(rate_str)
                except ValueError:
                    return 0.0

            width = int(v_stream.get("width") or 0)
            height = int(v_stream.get("height") or 0)
            fps = _parse_fps(v_stream.get("r_frame_rate", "0/1"))
            duration_s = float(fmt_data.get("duration") or v_stream.get("duration") or 0.0)
            if duration_s <= 0 or duration_s > max_duration_seconds:
                raise MediaIngestionError(
                    f"Probed duration ({duration_s}s) is unknown or exceeds max limit ({max_duration_seconds}s)."
                )
            file_size = int(fmt_data.get("size") or staging_video_mp4.stat().st_size)
            proxy_path = None
            if v_stream.get("codec_name") != "h264":
                proxy_path = staging_dir / "source_video_h264.mp4"
                proxy_cmd = ["ffmpeg", "-y", "-i", str(staging_video_mp4), "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(proxy_path)]
                proc = subprocess.run(proxy_cmd, capture_output=True, text=True, timeout=600)
                if proc.returncode or not proxy_path.is_file():
                    raise MediaIngestionError(f"H.264 editing proxy creation failed: {proc.stderr}")

            # 8. Atomic Finalization into projects/<project-id>/source/
            final_video = source_dir / "source_video.mp4"
            final_audio = source_dir / "source_audio.wav"
            final_transcript = source_dir / "transcript.json" if has_native_captions else None
            final_manifest = source_dir / "source_manifest.json"

            # Build Canonical Manifest
            acquired_timestamp = datetime.now(timezone.utc).isoformat()
            manifest_payload = {
                "version": "1.0",
                "project_id": project_id,
                "source_url": validated_url,
                "acquired_at": acquired_timestamp,
                "duration_seconds": duration_s,
                "resolution": [width, height],
                "fps": fps,
                "video_codec": v_stream.get("codec_name", "unknown"),
                "audio_codec": a_stream.get("codec_name", "pcm_s16le"),
                "sample_rate": int(a_stream.get("sample_rate") or 16000),
                "channels": int(a_stream.get("channels") or 1),
                "file_size_bytes": file_size,
                "has_native_captions": has_native_captions,
                "video_path": str(final_video),
                "audio_path": str(final_audio),
                "transcript_path": str(final_transcript) if has_native_captions else None,
                "metadata": metadata,
                "pipeline_type": self.pipeline_type,
                "master_video_path": str(final_video),
                "proxy_video_path": str(source_dir / proxy_path.name) if proxy_path else None,
            }

            tmp_manifest = staging_dir / "source_manifest.json.tmp"
            with open(tmp_manifest, "w", encoding="utf-8") as f:
                json.dump(manifest_payload, f, indent=2)
            self._commit_bundle({
                final_video: staging_video_mp4,
                final_audio: staging_audio_wav,
                source_dir / "source_video_h264.mp4": proxy_path,
                source_dir / "transcript.json": staging_transcript if has_native_captions else None,
                final_manifest: tmp_manifest,
            })

            return URLIngestResult(
                success=True,
                project_id=project_id,
                source_url=validated_url,
                video_path=str(final_video),
                audio_path=str(final_audio),
                transcript_path=str(final_transcript) if has_native_captions else None,
                manifest_path=str(final_manifest),
                has_native_captions=has_native_captions,
                duration_seconds=duration_s,
                resolution=(width, height),
                fps=fps,
                video_codec=v_stream.get("codec_name", "unknown"),
                audio_codec=a_stream.get("codec_name", "pcm_s16le"),
                file_size_bytes=file_size,
                acquired_at=acquired_timestamp,
            )

        except Exception as exc:
            logger.exception("URL ingestion failed for %s: %s", url, exc)
            return URLIngestResult(
                success=False,
                project_id=project_id,
                source_url=validated_url,
                error=str(exc),
            )
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)

    def ingest_local_file(
        self, local_path: str | Path, project_id: str, *, transcript_path: str | Path | None = None,
        max_duration_seconds: int = 3600, max_file_size_bytes: int = 2 * 1024**3,
    ) -> URLIngestResult:
        """Normalize a local media file into the same atomic source bundle."""
        self.validate_project_id(project_id)
        source = Path(local_path).expanduser().resolve()
        if not source.is_file():
            raise MediaIngestionError(f"Local media file not found: {source}")
        if (isinstance(max_file_size_bytes, bool) or not isinstance(max_file_size_bytes, int)
                or max_file_size_bytes <= 0):
            raise ValueError("max_file_size_bytes must be a positive integer")
        if (isinstance(max_duration_seconds, bool) or not isinstance(max_duration_seconds, int)
                or max_duration_seconds <= 0):
            raise ValueError("max_duration_seconds must be a positive integer")
        if source.stat().st_size > max_file_size_bytes:
            raise MediaIngestionError(f"Local media exceeds max_file_size_bytes={max_file_size_bytes}.")
        probe = self.probe_media_file(source)
        streams = probe.get("streams", [])
        video_stream = next((item for item in streams if item.get("codec_type") == "video"), None)
        if video_stream is None:
            raise MediaIngestionError("Local media contains no video stream.")
        try:
            duration = float(probe.get("format", {}).get("duration") or video_stream.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0.0
        if not math.isfinite(duration) or duration <= 0 or duration > max_duration_seconds:
            raise MediaIngestionError(f"Local media duration ({duration}s) is unknown or exceeds max_duration_seconds={max_duration_seconds}.")

        source_dir = self.projects_dir / project_id / "source"
        staging_dir = source_dir / f".staging_{uuid.uuid4().hex[:8]}"
        staging_dir.mkdir(parents=True, exist_ok=True)
        try:
            staged_video = staging_dir / "source_video.mp4"
            self.ensure_valid_mp4(source, staged_video)
            staged_audio = staging_dir / "source_audio.wav"
            self.extract_audio_fallback(staged_video, staged_audio)
            codec = str(video_stream.get("codec_name") or "unknown")
            staged_proxy = None
            if codec != "h264":
                staged_proxy = staging_dir / "source_video_h264.mp4"
                process = subprocess.run([
                    "ffmpeg", "-y", "-i", str(staged_video), "-c:v", "libx264", "-preset", "fast",
                    "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(staged_proxy),
                ], capture_output=True, text=True, timeout=600)
                if process.returncode != 0 or not staged_proxy.is_file():
                    raise MediaIngestionError(f"H.264 editing proxy creation failed: {process.stderr}")

            sidecar = Path(transcript_path).expanduser() if transcript_path else next(
                (source.with_suffix(suffix) for suffix in (".json", ".srt", ".vtt") if source.with_suffix(suffix).is_file()), None
            )
            staged_transcript = None
            transcript_suffix = None
            if sidecar and sidecar.is_file():
                transcript_suffix = sidecar.suffix.lower()
                if transcript_suffix not in {".json", ".srt", ".vtt"}:
                    raise MediaIngestionError("Transcript sidecar must be .json, .srt, or .vtt.")
                if transcript_suffix == ".json":
                    json.loads(sidecar.read_text(encoding="utf-8"))
                staged_transcript = staging_dir / f"transcript{transcript_suffix}"
                shutil.copy2(sidecar, staged_transcript)

            final_video = source_dir / "source_video.mp4"
            final_audio = source_dir / "source_audio.wav"
            final_transcript = source_dir / f"transcript{transcript_suffix}" if staged_transcript else None
            final_manifest = source_dir / "source_manifest.json"
            final_proxy = source_dir / "source_video_h264.mp4"
            video_probe = self.probe_media_file(staged_video)
            audio_probe = self.probe_media_file(staged_audio)
            audio_stream = next((item for item in audio_probe.get("streams", []) if item.get("codec_type") == "audio"), {})
            acquired = datetime.now(timezone.utc).isoformat()
            manifest = {
                "version": "1.0", "project_id": project_id, "source_url": source.as_uri(),
                "acquired_at": acquired, "duration_seconds": duration,
                "resolution": [int(video_stream.get("width") or 0), int(video_stream.get("height") or 0)],
                "fps": video_stream.get("r_frame_rate", "0/1"), "video_codec": codec,
                "audio_codec": audio_stream.get("codec_name", "pcm_s16le"), "sample_rate": 16000,
                "channels": 1, "file_size_bytes": staged_video.stat().st_size,
                "has_native_captions": bool(staged_transcript), "video_path": str(final_video),
                "audio_path": str(final_audio), "transcript_path": str(final_transcript) if final_transcript else None,
                "metadata": {"source_filename": source.name}, "pipeline_type": self.pipeline_type,
                "master_video_path": str(final_video), "proxy_video_path": str(final_proxy) if staged_proxy else None,
            }
            staged_manifest = staging_dir / "source_manifest.json.tmp"
            staged_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            self._commit_bundle({
                final_video: staged_video, final_audio: staged_audio, final_proxy: staged_proxy,
                source_dir / "transcript.json": staged_transcript if transcript_suffix == ".json" else None,
                source_dir / "transcript.srt": staged_transcript if transcript_suffix == ".srt" else None,
                source_dir / "transcript.vtt": staged_transcript if transcript_suffix == ".vtt" else None,
                final_manifest: staged_manifest,
            })
            return URLIngestResult(
                success=True, project_id=project_id, source_url=source.as_uri(), video_path=str(final_video),
                audio_path=str(final_audio), transcript_path=str(final_transcript) if final_transcript else None,
                manifest_path=str(final_manifest), has_native_captions=bool(staged_transcript),
                duration_seconds=duration, resolution=(int(video_stream.get("width") or 0), int(video_stream.get("height") or 0)),
                video_codec=codec, audio_codec=audio_stream.get("codec_name", "pcm_s16le"),
                file_size_bytes=final_video.stat().st_size, acquired_at=acquired,
            )
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)

    def review_ingested_media(
        self, ingest_result: URLIngestResult, tool_registry: Any = None
    ) -> dict[str, Any]:
        """Hand off acquired media to existing lib/source_media_review.py untouched."""
        if not ingest_result.success or not ingest_result.video_path:
            raise MediaIngestionError("Cannot review media: ingestion was not successful.")

        from lib.source_media_review import review_source_media

        reg = tool_registry or registry
        project_dir = self.projects_dir / ingest_result.project_id
        return review_source_media(
            [Path(ingest_result.video_path)],
            {"project_dir": project_dir, "pipeline_type": self.pipeline_type},
            reg,
        )
