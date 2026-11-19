"""Hardened FFmpeg argument builder, filtergraph escaper, and path jailer.

Guards against:
- Filtergraph command injection (';', ',', ':', '[', ']', single/double quotes)
- Path traversal across Windows/POSIX drives
- Windows Alternate Data Streams (ADS) and DOS device names
- IEEE 754 NaN/Infinity parameter injection
"""

from __future__ import annotations

import math
import os
import re
from pathlib import Path
from typing import Sequence

# Windows reserved device names
_RESERVED_NAMES = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})

# Safe filter names allowed in post-processing pipelines
_ALLOWED_FILTERS = frozenset({
    "cas", "unsharp", "hqdn3d", "scale", "crop", "setsar", "fps",
    "setpts", "asetpts", "aresample", "loudnorm", "format", "null",
})


def sanitize_float_param(
    value: float | int | str,
    name: str,
    min_val: float = 0.0,
    max_val: float = 1.0,
    default: float = 0.8,
) -> float:
    """Validate and clamp numeric filter parameters against NaN/Inf/Injection."""
    try:
        val = float(value)
    except (ValueError, TypeError):
        return default

    if not math.isfinite(val):
        raise ValueError(f"Parameter '{name}' must be a finite number; got {value!r}")
    if val < min_val or val > max_val:
        raise ValueError(f"Parameter '{name}' out of bounds [{min_val}, {max_val}]; got {val}")
    return val


def escape_filter_path(path: str | Path) -> str:
    """Escape a filesystem path for inclusion within an FFmpeg filter option.

    FFmpeg's filtergraph parser evaluates in two passes:
    Pass 1: Filtergraph syntax (breaks on ';', ',', '[', ']')
    Pass 2: Filter option syntax (breaks on ':', '\\', and quotes)
    """
    clean_path = str(Path(path).expanduser().resolve()).replace("\\", "/")

    # Check for Alternate Data Streams or null bytes
    if ":" in clean_path[2:] or "\0" in clean_path:
        raise ValueError(f"Potentially malicious path or Alternate Data Stream detected: {path}")

    # Pass 1 & 2 token escaping
    for ch in ("\\", ":", ",", "[", "]", ";", "="):
        clean_path = clean_path.replace(ch, "\\" + ch)
    # Double-pass escaping for single quotes
    clean_path = clean_path.replace("'", r"'\\\''")
    return clean_path


def build_cas_filter(strength: float = 0.8) -> str:
    """Safely build AMD FidelityFX CAS filter expression."""
    safe_strength = sanitize_float_param(strength, "cas_strength", min_val=0.0, max_val=1.0)
    return f"cas=strength={safe_strength:.4f}:planes=1"


def build_unsharp_fallback(strength: float = 0.8) -> str:
    """Safe fallback sharpening filter when CAS is unavailable."""
    safe_strength = sanitize_float_param(strength, "unsharp_strength", min_val=0.0, max_val=2.0)
    # 5x5 luma matrix with safe sharpening amount
    return f"unsharp=lx=5:ly=5:la={safe_strength:.2f}:cx=5:cy=5:ca=0.0"


def build_denoise_cas_chain(
    cas_strength: float = 0.45,
    denoise: bool = True,
    cas_available: bool = True,
) -> str:
    """Safely combine spatial denoise with AMD CAS / unsharp."""
    filters: list[str] = []
    if denoise:
        filters.append("hqdn3d=1.2:1.0:2.0:1.5")
    if cas_available:
        filters.append(build_cas_filter(cas_strength))
    else:
        filters.append(build_unsharp_fallback(cas_strength))
    return ",".join(filters)


class PathJailViolation(Exception):
    """Raised when an operation attempts to escape its designated filesystem jail."""


def resolve_jailed_path(
    user_input_path: str | Path,
    jail_root: Path,
    allow_subdirs: bool = True,
) -> Path:
    """Canonicalize and verify a path strictly resides within a jail root.

    Defends against:
    - Traversal via '..' or symlinks/junctions
    - Absolute path override on Windows/POSIX
    - DOS reserved filenames
    - Null bytes
    """
    raw_str = str(user_input_path).strip()
    if "\0" in raw_str:
        raise PathJailViolation("Path contains forbidden null byte")

    # Prevent absolute path component hijacking on Windows/POSIX
    path_obj = Path(raw_str)
    if path_obj.is_absolute() or path_obj.drive:
        # Strip drive or root anchor if relative path was expected
        clean_rel = raw_str.lstrip("/\\")
        if re.match(r"^[A-Za-z]:", clean_rel):
            clean_rel = clean_rel[2:].lstrip("/\\")
        path_obj = Path(clean_rel)

    jail_canonical = jail_root.resolve()
    target = (jail_canonical / path_obj).resolve()

    # Verify DOS device names in any path segment
    for part in target.parts:
        stem = Path(part).stem.upper()
        if stem in _RESERVED_NAMES:
            raise PathJailViolation(f"Forbidden Windows device name in path: {stem}")

    # Strict containment check
    try:
        target.relative_to(jail_canonical)
    except ValueError:
        raise PathJailViolation(f"Path traversal detected: '{user_input_path}' escapes '{jail_root}'")

    if not allow_subdirs and target.parent != jail_canonical:
        raise PathJailViolation(f"Subdirectories forbidden in target jail: '{target}'")

    # Verify symlink realpath containment (NTFS junction / symlink defense)
    real_target = Path(os.path.realpath(target))
    real_jail = Path(os.path.realpath(jail_canonical))
    try:
        real_target.relative_to(real_jail)
    except ValueError:
        raise PathJailViolation(f"Symlink/Junction traversal detected: '{real_target}' points outside '{real_jail}'")

    return target
