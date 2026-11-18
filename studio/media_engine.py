"""Pro NLE media engine for Studio: FFmpeg PCM waveforms, filmstrip frames,
local music library scanning, and safe local file browsing.

All derived caches live strictly under ``.studio/cache/`` (outside ``projects/``)
so Backlot's filesystem watcher is never triggered by UI inspection requests.
"""

from __future__ import annotations

import array
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from lib.paths import REPO_ROOT

STUDIO_CACHE_DIR = REPO_ROOT / ".studio" / "cache"
STUDIO_UPLOADS_DIR = REPO_ROOT / ".studio" / "uploads"

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".ts"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".aiff", ".aif"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
ALLOWED_UPLOAD_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS | IMAGE_EXTENSIONS | {".srt", ".vtt", ".ass"}
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB cap


def _cache_key(path: Path, extra: str = "") -> str:
    st = path.stat()
    raw = f"{path.resolve()}|{st.st_mtime_ns}|{st.st_size}|{extra}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def probe_duration_seconds(media_path: Path) -> float:
    """Fast ffprobe duration lookup (seconds). Returns 0.0 on failure."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not media_path.is_file():
        return 0.0
    try:
        proc = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(media_path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        val = float((proc.stdout or "").strip())
        return val if math.isfinite(val) and val > 0 else 0.0
    except Exception:
        return 0.0


def extract_waveform_peaks(
    media_path: Path,
    *,
    bins: int = 400,
    cache_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Decode audio track to mono 8kHz s16le PCM via FFmpeg and compute normalized peaks."""
    clamped_bins = max(32, min(2000, int(bins)))
    root_cache = (cache_dir or STUDIO_CACHE_DIR) / "waveforms"
    root_cache.mkdir(parents=True, exist_ok=True)
    key = _cache_key(media_path, f"wf_{clamped_bins}")
    cache_file = root_cache / f"{key}.json"
    if cache_file.is_file():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if isinstance(cached, dict) and isinstance(cached.get("peaks"), list):
                return cached
        except (OSError, json.JSONDecodeError):
            pass

    duration = probe_duration_seconds(media_path)
    ffmpeg = shutil.which("ffmpeg")
    peaks: list[float] = []
    has_audio = False

    if ffmpeg and media_path.is_file():
        try:
            proc = subprocess.run(
                [
                    ffmpeg,
                    "-v",
                    "error",
                    "-i",
                    str(media_path),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "8000",
                    "-f",
                    "s16le",
                    "pipe:1",
                ],
                capture_output=True,
                timeout=45,
                check=False,
            )
            raw = proc.stdout or b""
            n_bytes = len(raw) - (len(raw) % 2)
            if n_bytes >= 2:
                has_audio = True
                samples = array.array("h")
                samples.frombytes(raw[:n_bytes])
                total = len(samples)
                if duration <= 0.0:
                    duration = round(total / 8000.0, 3)
                step = max(1, total // clamped_bins)
                raw_peaks: list[float] = []
                for i in range(clamped_bins):
                    lo = int(i * total / clamped_bins)
                    hi = max(lo + 1, min(total, int((i + 1) * total / clamped_bins)))
                    if lo >= total:
                        raw_peaks.append(0.0)
                        continue
                    # Fast peak + RMS blend for crisp NLE waveform readability
                    chunk = samples[lo:hi]
                    max_abs = max((abs(s) for s in chunk), default=0)
                    raw_peaks.append(max_abs / 32768.0)
                max_val = max(raw_peaks) if raw_peaks else 0.0
                if max_val > 1e-6:
                    peaks = [round(min(1.0, p / max_val), 4) for p in raw_peaks]
                else:
                    peaks = [0.0] * clamped_bins
        except Exception:
            peaks = []

    if not peaks:
        peaks = [0.0] * clamped_bins

    result = {
        "duration_seconds": round(duration, 3),
        "bins": clamped_bins,
        "has_audio": has_audio,
        "peaks": peaks,
    }
    try:
        cache_file.write_text(json.dumps(result), encoding="utf-8")
    except OSError:
        pass
    return result


def extract_filmstrip_frames(
    media_path: Path,
    *,
    count: int = 12,
    width: int = 180,
    cache_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Extract evenly spaced JPEG filmstrip frames into ``.studio/cache/filmstrips/{key}/``."""
    clamped_count = max(4, min(32, int(count)))
    clamped_width = max(80, min(360, int(width)))
    root_cache = (cache_dir or STUDIO_CACHE_DIR) / "filmstrips"
    key = _cache_key(media_path, f"fs_{clamped_count}_{clamped_width}")
    out_dir = root_cache / key
    meta_file = out_dir / "meta.json"

    if meta_file.is_file():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            if isinstance(meta, dict) and isinstance(meta.get("frames"), list) and meta["frames"]:
                return meta
        except (OSError, json.JSONDecodeError):
            pass

    duration = probe_duration_seconds(media_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    frames: list[dict[str, Any]] = []

    if ffmpeg and media_path.is_file() and duration > 0.05:
        fps_rate = clamped_count / max(duration, 0.5)
        pattern = str(out_dir / "frame_%03d.jpg")
        try:
            subprocess.run(
                [
                    ffmpeg,
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    str(media_path),
                    "-vf",
                    f"fps={fps_rate:.6f},scale={clamped_width}:-2",
                    "-q:v",
                    "5",
                    "-frames:v",
                    str(clamped_count),
                    pattern,
                ],
                capture_output=True,
                timeout=45,
                check=False,
            )
            generated = sorted(out_dir.glob("frame_*.jpg"))
            n = len(generated)
            for idx, fp in enumerate(generated):
                ts = round((idx + 0.5) * (duration / max(n, 1)), 3)
                frames.append({"index": idx, "timestamp": ts, "file": fp.name})
        except Exception:
            frames = []

    result = {
        "cache_key": key,
        "duration_seconds": round(duration, 3),
        "count": len(frames),
        "width": clamped_width,
        "frames": frames,
    }
    try:
        meta_file.write_text(json.dumps(result), encoding="utf-8")
    except OSError:
        pass
    return result


def resolve_filmstrip_frame(cache_key: str, frame_index: int, cache_dir: Optional[Path] = None) -> Optional[Path]:
    """Safely locate a cached filmstrip JPEG by hex cache_key + integer index."""
    if not re.fullmatch(r"[0-9a-f]{20}", cache_key):
        return None
    if frame_index < 0 or frame_index > 100:
        return None
    root_cache = (cache_dir or STUDIO_CACHE_DIR) / "filmstrips"
    target = (root_cache / cache_key / f"frame_{frame_index + 1:03d}.jpg").resolve()
    try:
        target.relative_to(root_cache.resolve())
    except ValueError:
        return None
    return target if target.is_file() else None


def get_music_library_dir() -> Path:
    env_dir = (os.environ.get("MUSIC_LIBRARY_DIR") or "").strip()
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    return (REPO_ROOT / "music_library").resolve()


def list_music_library() -> dict[str, Any]:
    """Scan local royalty-free music_library/ directory."""
    lib_dir = get_music_library_dir()
    tracks: list[dict[str, Any]] = []
    if lib_dir.is_dir():
        for p in sorted(lib_dir.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            rel = p.relative_to(lib_dir).as_posix()
            tracks.append({
                "name": p.stem,
                "filename": p.name,
                "rel_path": rel,
                "extension": p.suffix.lower().lstrip("."),
                "size_bytes": p.stat().st_size,
                "stream_url": f"/music/{rel}",
            })
    return {
        "library_dir": str(lib_dir),
        "exists": lib_dir.is_dir(),
        "count": len(tracks),
        "tracks": tracks,
    }


def sanitize_upload_filename(filename: str) -> str:
    """Return a safe filename preserving an allowed media extension."""
    base = Path(filename or "upload.mp4").name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(base).stem).strip("._-") or "media"
    ext = Path(base).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise ValueError(
            f"Unsupported file extension '{ext}'. Allowed: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}"
        )
    return f"{stem[:64]}{ext}"


def browse_local_media(raw_path: Optional[str] = None) -> dict[str, Any]:
    """Safe local directory browser for selecting source video/audio/image files."""
    if raw_path and raw_path.strip():
        target = Path(raw_path).expanduser().resolve()
    else:
        target = REPO_ROOT.resolve()
    if not target.exists() or not target.is_dir():
        target = REPO_ROOT.resolve()

    parent = str(target.parent) if target.parent != target else None
    dirs: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    try:
        entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError:
        entries = []

    for entry in entries:
        if entry.name.startswith(".") and entry.name not in (".studio",):
            continue
        if entry.name in {"node_modules", "__pycache__", ".git", ".venv"}:
            continue
        try:
            if entry.is_dir():
                if len(dirs) < 80:
                    dirs.append({"name": entry.name, "path": str(entry)})
            elif entry.is_file():
                ext = entry.suffix.lower()
                if ext in ALLOWED_UPLOAD_EXTENSIONS and len(files) < 120:
                    kind = (
                        "video"
                        if ext in VIDEO_EXTENSIONS
                        else "audio"
                        if ext in AUDIO_EXTENSIONS
                        else "image"
                        if ext in IMAGE_EXTENSIONS
                        else "subtitle"
                    )
                    files.append({
                        "name": entry.name,
                        "path": str(entry),
                        "kind": kind,
                        "size_bytes": entry.stat().st_size,
                    })
        except OSError:
            continue

    quick_roots = [
        {"label": "Workspace", "path": str(REPO_ROOT)},
        {"label": "Uploads", "path": str(STUDIO_UPLOADS_DIR)},
        {"label": "Projects", "path": str(REPO_ROOT / "projects")},
        {"label": "Home", "path": str(Path.home())},
    ]
    return {
        "path": str(target),
        "parent": parent,
        "quick_roots": [r for r in quick_roots if Path(r["path"]).is_dir()],
        "dirs": dirs,
        "files": files,
    }
