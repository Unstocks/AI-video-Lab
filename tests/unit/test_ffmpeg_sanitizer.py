"""Unit tests for lib/ffmpeg_sanitizer.py."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from lib.ffmpeg_sanitizer import (
    PathJailViolation,
    build_cas_filter,
    build_denoise_cas_chain,
    build_unsharp_fallback,
    escape_filter_path,
    resolve_jailed_path,
    sanitize_float_param,
)


def test_sanitize_float_param_valid():
    assert sanitize_float_param(0.45, "cas") == 0.45
    assert sanitize_float_param("0.75", "cas") == 0.75
    assert sanitize_float_param(1.0, "cas") == 1.0


def test_sanitize_float_param_out_of_bounds():
    with pytest.raises(ValueError, match="out of bounds"):
        sanitize_float_param(1.5, "cas", min_val=0.0, max_val=1.0)
    with pytest.raises(ValueError, match="out of bounds"):
        sanitize_float_param(-0.1, "cas", min_val=0.0, max_val=1.0)


def test_sanitize_float_param_nan_and_inf():
    with pytest.raises(ValueError, match="must be a finite number"):
        sanitize_float_param(float("nan"), "cas")
    with pytest.raises(ValueError, match="must be a finite number"):
        sanitize_float_param(float("inf"), "cas")


def test_sanitize_float_param_invalid_string():
    assert sanitize_float_param("not_a_number", "cas", default=0.5) == 0.5


def test_escape_filter_path_basic(tmp_path: Path):
    target = tmp_path / "simple_video.mp4"
    target.touch()
    escaped = escape_filter_path(target)
    assert "simple_video.mp4" in escaped
    assert "\\" not in escaped or "\\:" in escaped


def test_escape_filter_path_special_characters(tmp_path: Path):
    bad_dir = tmp_path / "weird [dir],name"
    bad_dir.mkdir()
    target = bad_dir / "clip's,final.mp4"
    target.touch()
    escaped = escape_filter_path(target)
    # Check that commas, brackets, and single quotes were escaped
    assert r"\," in escaped
    assert r"\[" in escaped
    assert r"\]" in escaped
    assert r"'\\\''" in escaped


def test_escape_filter_path_ads_and_null_byte_blocked(tmp_path: Path):
    with pytest.raises(ValueError, match="Potentially malicious"):
        escape_filter_path("video.mp4\0evil")


def test_build_cas_and_unsharp():
    cas = build_cas_filter(0.45)
    assert cas == "cas=strength=0.4500:planes=1"

    unsharp = build_unsharp_fallback(0.8)
    assert "unsharp=lx=5:ly=5:la=0.80" in unsharp


def test_build_denoise_cas_chain():
    chain_cas = build_denoise_cas_chain(0.45, denoise=True, cas_available=True)
    assert "hqdn3d=" in chain_cas
    assert "cas=strength=0.4500" in chain_cas

    chain_unsharp = build_denoise_cas_chain(0.45, denoise=True, cas_available=False)
    assert "hqdn3d=" in chain_unsharp
    assert "unsharp=" in chain_unsharp


def test_resolve_jailed_path_valid(tmp_path: Path):
    jail = tmp_path / "project_root"
    jail.mkdir()
    target = jail / "source" / "clip.mp4"
    target.parent.mkdir()
    target.touch()

    resolved = resolve_jailed_path("source/clip.mp4", jail)
    assert resolved == target.resolve()


def test_resolve_jailed_path_traversal_blocked(tmp_path: Path):
    jail = tmp_path / "project_root"
    jail.mkdir()

    with pytest.raises(PathJailViolation, match="Path traversal detected"):
        resolve_jailed_path("../outside.mp4", jail)

    with pytest.raises(PathJailViolation, match="Path traversal detected"):
        resolve_jailed_path("../../etc/passwd", jail)


def test_resolve_jailed_path_reserved_name_blocked(tmp_path: Path):
    jail = tmp_path / "project_root"
    jail.mkdir()

    with pytest.raises(PathJailViolation, match="Forbidden Windows device name"):
        resolve_jailed_path("con.mp4", jail)
    with pytest.raises(PathJailViolation, match="Forbidden Windows device name"):
        resolve_jailed_path("aux.txt", jail)
