"""Sidecar ``<clip>.layout.json`` contract shared by Reframe v2, SubtitleGen, and Studio UI.

Schema::

    {
      "ranges": [
        {"start": 0.0, "end": 8.4, "layout": "track"},
        {"start": 8.4, "end": 22.1, "layout": "split"},
        {"start": 22.1, "end": 34.0, "layout": "general", "content": [0.29, 0.71]}
      ],
      "punch_ins": [3.2, 24.5]
    }

All helpers are pure Python (zero media dependencies) and fail soft when a
sidecar is missing or malformed.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Sequence

VALID_LAYOUTS = frozenset({"track", "split", "general", "alternate"})


def sidecar_path(video_path: str | Path) -> Path:
    """Return canonical sidecar path ``<video_path>.layout.json``."""
    p = Path(video_path)
    return Path(f"{p}.layout.json")


def normalise(ranges: Sequence[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Sort, drop empty/invalid entries, and merge contiguous identical layout ranges."""
    cleaned: list[dict[str, Any]] = []
    for raw in ranges or []:
        if not isinstance(raw, dict):
            continue
        try:
            start = round(max(0.0, float(raw["start"])), 3)
            end = round(float(raw["end"]), 3)
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start:
            continue
        layout = str(raw.get("layout", "track")).strip().lower()
        if layout not in VALID_LAYOUTS:
            layout = "track"
        entry: dict[str, Any] = {"start": start, "end": end, "layout": layout}
        content = raw.get("content")
        if (
            isinstance(content, (list, tuple))
            and len(content) == 2
            and all(isinstance(v, (int, float)) for v in content)
        ):
            entry["content"] = [round(float(content[0]), 4), round(float(content[1]), 4)]
        cleaned.append(entry)

    cleaned.sort(key=lambda r: (r["start"], r["end"]))
    merged: list[dict[str, Any]] = []
    for item in cleaned:
        if (
            merged
            and merged[-1]["layout"] == item["layout"]
            and merged[-1].get("content") == item.get("content")
            and abs(merged[-1]["end"] - item["start"]) <= 0.05
        ):
            merged[-1]["end"] = max(merged[-1]["end"], item["end"])
        else:
            merged.append(dict(item))
    return merged


def write(
    video_path: str | Path,
    ranges: Sequence[dict[str, Any]],
    *,
    punch_ins: Sequence[float] | None = None,
) -> Path:
    """Atomically write ``<video_path>.layout.json``."""
    target = sidecar_path(video_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "ranges": normalise(ranges),
        "punch_ins": sorted(
            {round(float(t), 3) for t in (punch_ins or []) if float(t) >= 0.0}
        ),
    }
    raw = json.dumps(payload, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=".layout_", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(raw)
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return target


def read_payload(video_path: str | Path) -> dict[str, Any]:
    """Read full sidecar payload ``{"ranges": [...], "punch_ins": [...]}`` (empty if missing)."""
    target = sidecar_path(video_path)
    if not target.is_file():
        return {"ranges": [], "punch_ins": []}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ranges": [], "punch_ins": []}
    if isinstance(data, list):
        return {"ranges": normalise(data), "punch_ins": []}
    if not isinstance(data, dict):
        return {"ranges": [], "punch_ins": []}
    raw_punches = data.get("punch_ins") or []
    punches: list[float] = []
    if isinstance(raw_punches, list):
        for v in raw_punches:
            try:
                f = float(v)
                if f >= 0:
                    punches.append(round(f, 3))
            except (TypeError, ValueError):
                continue
    return {"ranges": normalise(data.get("ranges")), "punch_ins": sorted(set(punches))}


def read(video_path: str | Path) -> list[dict[str, Any]]:
    """Read normalised layout ranges list from ``<video_path>.layout.json``."""
    return read_payload(video_path)["ranges"]


def split_ranges(ranges: Sequence[dict[str, Any]] | None) -> list[tuple[float, float]]:
    """Extract ``[(start, end), ...]`` intervals where layout is ``split``."""
    out: list[tuple[float, float]] = []
    for item in normalise(ranges):
        if item["layout"] == "split":
            out.append((float(item["start"]), float(item["end"])))
    return out


def in_split(timestamp_seconds: float, ranges: Sequence[dict[str, Any]] | Sequence[tuple[float, float]] | None) -> bool:
    """Return True if ``timestamp_seconds`` falls inside any ``split`` range."""
    t = float(timestamp_seconds)
    for item in ranges or []:
        if isinstance(item, dict):
            if str(item.get("layout", "")).lower() != "split":
                continue
            s, e = float(item["start"]), float(item["end"])
        else:
            s, e = float(item[0]), float(item[1])
        if s <= t < e:
            return True
    return False


def remap(
    ranges: Sequence[dict[str, Any]] | None,
    offset_seconds: float,
    end_seconds: float | None = None,
) -> list[dict[str, Any]]:
    """Slice and rebase layout ranges to ``[0, end - offset]`` after a clip trim/recut."""
    off = float(offset_seconds)
    hi = float(end_seconds) if end_seconds is not None else float("inf")
    remapped: list[dict[str, Any]] = []
    for item in normalise(ranges):
        s = max(float(item["start"]), off)
        e = min(float(item["end"]), hi)
        if e <= s:
            continue
        entry: dict[str, Any] = {
            "start": round(s - off, 3),
            "end": round(e - off, 3),
            "layout": item["layout"],
        }
        if "content" in item:
            entry["content"] = list(item["content"])
        remapped.append(entry)
    return normalise(remapped)
