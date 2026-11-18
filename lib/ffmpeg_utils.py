"""Small shared helpers for FFmpeg filtergraph values."""

from pathlib import Path


def escape_ffmpeg_filter_path(path: str | Path) -> str:
    """Escape a filesystem path for use as a value in an FFmpeg filtergraph."""
    value = str(Path(path).expanduser().resolve()).replace("\\", "/")
    for char in ("\\", ":", "'", ",", "[", "]"):
        value = value.replace(char, "\\" + char)
    return value
