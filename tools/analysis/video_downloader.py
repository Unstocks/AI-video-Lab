"""Video downloader tool wrapping yt-dlp.

Downloads video, audio, or subtitles from YouTube, Shorts, Instagram Reels,
TikTok, and 1000+ other sites. Designed for reference video analysis — downloads
at analysis quality (720p), not production quality.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from lib import ssrf_guard
from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolStability,
    ToolStatus,
    ToolTier,
    ToolRuntime,
)


class VideoDownloader(BaseTool):
    name = "video_downloader"
    version = "0.1.0"
    tier = ToolTier.SOURCE
    capability = "source_ingest"
    provider = "yt-dlp"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = ["python:yt_dlp"]
    install_instructions = (
        "Install yt-dlp: pip install yt-dlp\n"
        "For YouTube support, also install Deno (JS runtime): "
        "https://deno.land/#installation\n"
        "Without Deno, YouTube downloads may fail but other platforms still work."
    )
    agent_skills = ["video-download"]

    capabilities = [
        "download_video",
        "download_audio",
        "download_subtitles",
        "extract_metadata",
    ]

    best_for = [
        "downloading reference video from URL",
        "extracting audio from online video",
        "downloading subtitles from YouTube",
        "getting video metadata without downloading",
    ]

    not_good_for = [
        "downloading entire playlists",
        "downloading DRM-protected content",
    ]

    input_schema = {
        "type": "object",
        "required": ["url", "output_dir"],
        "properties": {
            "url": {"type": "string", "description": "Video URL to download"},
            "output_dir": {"type": "string", "description": "Directory for downloaded files"},
            "format": {
                "type": "string",
                "enum": ["video", "audio_only", "subtitles_only", "metadata_only"],
                "default": "video",
                "description": "What to download",
            },
            "max_resolution": {
                "type": "string",
                "enum": ["360p", "480p", "720p", "1080p"],
                "default": "720p",
                "description": "Maximum video resolution (for analysis, 720p is sufficient)",
            },
            "max_duration_seconds": {
                "type": "integer",
                "default": 600,
                "description": "Reject videos longer than this (safety limit)",
            },
            "max_file_size_bytes": {"type": "integer", "minimum": 1, "default": 2147483648},
            "allowed_extractors": {"type": ["array", "null"], "items": {"type": "string"}, "default": None},
        },
    }

    output_schema = {
        "type": "object",
        "properties": {
            "video_path": {"type": ["string", "null"]},
            "audio_path": {"type": ["string", "null"]},
            "subtitle_path": {"type": ["string", "null"]},
            "metadata": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "duration": {"type": "number"},
                    "uploader": {"type": "string"},
                    "upload_date": {"type": "string"},
                    "description": {"type": "string"},
                    "view_count": {"type": "integer"},
                    "like_count": {"type": "integer"},
                },
            },
            "platform": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=2000,
        network_required=True,
    )
    idempotency_key_fields = ["url", "format", "max_resolution"]
    side_effects = ["downloads media files to output_dir"]
    resume_support_value = "from_start"
    user_visible_verification = [
        "Check downloaded file plays correctly",
        "Verify resolution matches requested max",
    ]

    # --- Resolution mapping ---
    _RES_MAP = {
        "360p": 360,
        "480p": 480,
        "720p": 720,
        "1080p": 1080,
    }

    def _detect_platform(self, url: str) -> str:
        """Detect platform from URL."""
        url_lower = url.lower()
        if "youtube.com/shorts" in url_lower or "youtu.be" in url_lower and "/shorts" in url_lower:
            return "shorts"
        if "youtube.com" in url_lower or "youtu.be" in url_lower:
            return "youtube"
        if "instagram.com" in url_lower:
            return "instagram"
        if "tiktok.com" in url_lower:
            return "tiktok"
        if "vimeo.com" in url_lower:
            return "vimeo"
        if "twitter.com" in url_lower or "x.com" in url_lower:
            return "twitter"
        return "other_url"

    @staticmethod
    def _max_available_height(info: dict[str, Any]) -> int:
        best = 0
        for fmt in info.get("formats") or ():
            if not isinstance(fmt, dict):
                continue
            if fmt.get("vcodec") == "none":
                continue
            h = fmt.get("height")
            if isinstance(h, (int, float)) and h > best:
                best = int(h)
        if best == 0:
            h = info.get("height")
            if isinstance(h, (int, float)) and h > 0:
                best = int(h)
        return best

    def _extract_metadata(self, url: str, allowed_extractors: list[str] | None = None) -> dict:
        """Extract metadata without downloading."""
        import yt_dlp

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "socket_timeout": 30,
            "extractor_retries": 2,
            "fragment_retries": 2,
            "file_access_retries": 1,
            "skip_download": True,
        }
        if allowed_extractors:
            ydl_opts["allowed_extractors"] = allowed_extractors
        try:
            with ssrf_guard.guarded():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if info is None:
                        return {"error": "No info extracted", "title": "", "duration": 0}
                    ssrf_guard.assert_public_urls(info, resolve_dns=False)
                    return {
                        "title": info.get("title", ""),
                        "duration": info.get("duration", 0),
                        "uploader": info.get("uploader", info.get("channel", "")),
                        "upload_date": info.get("upload_date", ""),
                        "description": (info.get("description", "") or "")[:500],
                        "view_count": info.get("view_count", 0),
                        "like_count": info.get("like_count", 0),
                        "resolution": f"{info.get('width', 0)}x{info.get('height', 0)}",
                        "max_available_height": self._max_available_height(info),
                        "fps": info.get("fps", 0),
                    }
        except Exception as e:
            return {"error": str(e), "title": "", "duration": 0}

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        url = inputs["url"]
        try:
            ssrf_guard.assert_public_url(url, resolve_dns=False)
        except ssrf_guard.SSRFBlockedError as exc:
            return ToolResult(success=False, error=str(exc))
        output_dir = Path(inputs["output_dir"])
        dl_format = inputs.get("format", "video")
        max_res = inputs.get("max_resolution", "720p")
        max_duration = inputs.get("max_duration_seconds", 600)
        max_file_size = inputs.get("max_file_size_bytes", 2 * 1024**3)
        if isinstance(max_file_size, bool) or not isinstance(max_file_size, int) or max_file_size <= 0:
            return ToolResult(success=False, error="max_file_size_bytes must be a positive integer")

        output_dir.mkdir(parents=True, exist_ok=True)
        platform = self._detect_platform(url)
        start = time.time()

        # Step 1: Always get metadata first
        allowed_extractors = inputs.get("allowed_extractors")
        metadata = self._extract_metadata(url, allowed_extractors)
        if metadata.get("error"):
            return ToolResult(success=False, error=str(metadata["error"]), data={"metadata": metadata, "platform": platform})

        # Check duration limit
        duration = metadata.get("duration", 0)
        if dl_format == "video" and (not duration or duration <= 0):
            return ToolResult(success=False, error="Video duration is unknown; refusing unbounded download.", data={"metadata": metadata, "platform": platform})
        if duration and duration > max_duration:
            return ToolResult(
                success=False,
                error=(
                    f"Video is {duration}s, exceeds max_duration_seconds={max_duration}. "
                    f"Increase the limit or use a shorter video."
                ),
                data={"metadata": metadata, "platform": platform},
            )

        if dl_format == "metadata_only":
            return ToolResult(
                success=True,
                data={
                    "video_path": None,
                    "audio_path": None,
                    "subtitle_path": None,
                    "metadata": metadata,
                    "platform": platform,
                },
                duration_seconds=round(time.time() - start, 2),
            )

        video_path = None
        audio_path = None
        subtitle_path = None

        try:
            if dl_format == "video":
                video_path, audio_path = self._download_video(
                    url, output_dir, max_res, allowed_extractors, max_file_size
                )
            elif dl_format == "audio_only":
                audio_path = self._download_audio(url, output_dir, allowed_extractors, max_file_size)
            elif dl_format == "subtitles_only":
                subtitle_path = self._download_subtitles(url, output_dir, allowed_extractors, max_file_size)
        except Exception as e:
            elapsed = time.time() - start
            return ToolResult(
                success=False,
                error=f"Download failed: {e}",
                data={"metadata": metadata, "platform": platform},
                duration_seconds=round(elapsed, 2),
            )

        elapsed = time.time() - start
        artifacts = [p for p in [video_path, audio_path, subtitle_path] if p]
        oversized = [p for p in artifacts if Path(p).is_file() and Path(p).stat().st_size > max_file_size]
        if oversized:
            for path in oversized:
                Path(path).unlink(missing_ok=True)
            return ToolResult(success=False, error=f"Downloaded file exceeds max_file_size_bytes={max_file_size}",
                              data={"metadata": metadata, "platform": platform}, duration_seconds=round(elapsed, 2))

        return ToolResult(
            success=True,
            data={
                "video_path": video_path,
                "audio_path": audio_path,
                "subtitle_path": subtitle_path,
                "metadata": metadata,
                "platform": platform,
            },
            artifacts=artifacts,
            duration_seconds=round(elapsed, 2),
        )

    def _download_video(
        self, url: str, output_dir: Path, max_res: str, allowed_extractors: list[str] | None = None,
        max_file_size_bytes: int = 2 * 1024**3,
    ) -> tuple[str | None, str | None]:
        """Download video + extract audio track."""
        import yt_dlp

        height = self._RES_MAP.get(max_res, 720)
        video_out = str(output_dir / "reference_video.%(ext)s")

        ydl_opts = {
            "format": f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best",
            "merge_output_format": "mp4",
            "outtmpl": video_out,
            "noplaylist": True,
            "max_filesize": max_file_size_bytes,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 30,
            "extractor_retries": 2,
            "fragment_retries": 2,
            "file_access_retries": 1,
        }
        if allowed_extractors:
            ydl_opts["allowed_extractors"] = allowed_extractors
        with ssrf_guard.guarded():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

        # Find the downloaded video file
        video_path = self._find_downloaded(output_dir, "reference_video", ["mp4", "mkv", "webm"])

        # Extract audio separately for transcription
        audio_path = None
        if video_path:
            audio_out = output_dir / "reference_audio.wav"
            try:
                audio_cmd = [
                    "ffmpeg", "-y",
                    "-i", video_path,
                    "-vn",
                    "-acodec", "pcm_s16le",
                    "-ar", "16000",
                    "-ac", "1",
                    str(audio_out),
                ]
                self.run_command(audio_cmd, timeout=120)
                if audio_out.exists():
                    audio_path = str(audio_out)
            except Exception:
                pass  # Audio extraction is optional

        return video_path, audio_path

    def _download_audio(self, url: str, output_dir: Path, allowed_extractors: list[str] | None = None,
                        max_file_size_bytes: int = 2 * 1024**3) -> str | None:
        """Download audio only."""
        import yt_dlp

        audio_out = str(output_dir / "reference_audio.%(ext)s")
        ydl_opts = {
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "0",
            }],
            "outtmpl": audio_out,
            "noplaylist": True,
            "max_filesize": max_file_size_bytes,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 30,
            "extractor_retries": 2,
            "fragment_retries": 2,
            "file_access_retries": 1,
        }
        if allowed_extractors:
            ydl_opts["allowed_extractors"] = allowed_extractors
        with ssrf_guard.guarded():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        return self._find_downloaded(output_dir, "reference_audio", ["wav", "mp3", "m4a", "opus"])

    def _download_subtitles(self, url: str, output_dir: Path, allowed_extractors: list[str] | None = None,
                            max_file_size_bytes: int = 2 * 1024**3) -> str | None:
        """Download subtitles only."""
        import yt_dlp

        sub_out = str(output_dir / "reference_subs.%(ext)s")
        ydl_opts = {
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["en"],
            "subtitlesformat": "srt",
            "skip_download": True,
            "outtmpl": sub_out,
            "noplaylist": True,
            "max_filesize": max_file_size_bytes,
            "socket_timeout": 30,
            "extractor_retries": 2,
            "fragment_retries": 2,
            "file_access_retries": 1,
            "quiet": True,
            "no_warnings": True,
        }
        if allowed_extractors:
            ydl_opts["allowed_extractors"] = allowed_extractors
        try:
            with ssrf_guard.guarded():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
        except ssrf_guard.SSRFBlockedError:
            raise
        except Exception:
            pass
        return self._find_downloaded(output_dir, "reference_subs", ["srt", "vtt", "ass"])

    def _find_downloaded(
        self, output_dir: Path, prefix: str, extensions: list[str]
    ) -> str | None:
        """Find a downloaded file by prefix and possible extensions."""
        for ext in extensions:
            candidates = list(output_dir.glob(f"{prefix}*.{ext}"))
            if candidates:
                return str(candidates[0])
        return None
