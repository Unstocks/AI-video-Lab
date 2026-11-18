"""Small shared helpers for FFmpeg filtergraph values."""

from pathlib import Path


def escape_ffmpeg_filter_path(path: str | Path) -> str:
    """Escape a filesystem path for use inside a single-quoted FFmpeg filtergraph value.

    FFmpeg runs two token-parsing passes on filter options (filtergraph + filter
    argument), so a literal apostrophe inside ``'...'`` must be escaped as
    ``'\\\\\\''`` to survive both passes cleanly on Windows and POSIX.
    """
    value = str(Path(path).expanduser().resolve()).replace("\\", "/")
    for char in ("\\", ":", ",", "[", "]"):
        value = value.replace(char, "\\" + char)
    value = value.replace("'", r"'\\\''")
    return value
