"""Unit tests for lib.layout_ranges (<clip>.mp4.layout.json sidecar contract)."""

from __future__ import annotations

from pathlib import Path

from lib import layout_ranges


def test_write_read_roundtrip_and_normalise_merges_adjacent(tmp_path: Path):
    clip = tmp_path / "clip_01.mp4"
    ranges = [
        {"start": 0.0, "end": 4.0, "layout": "track"},
        {"start": 4.0, "end": 8.4, "layout": "track"},  # contiguous same layout -> merged
        {"start": 8.4, "end": 22.1, "layout": "split"},
        {"start": 22.1, "end": 34.0, "layout": "general", "content": [0.29, 0.71]},
        {"start": 10.0, "end": 10.0, "layout": "track"},  # zero-length dropped
    ]
    sidecar = layout_ranges.write(clip, ranges, punch_ins=[24.5, 3.2, 3.2])
    assert sidecar == Path(f"{clip}.layout.json")
    assert sidecar.is_file()

    payload = layout_ranges.read_payload(clip)
    assert payload["punch_ins"] == [3.2, 24.5]
    assert payload["ranges"] == [
        {"start": 0.0, "end": 8.4, "layout": "track"},
        {"start": 8.4, "end": 22.1, "layout": "split"},
        {"start": 22.1, "end": 34.0, "layout": "general", "content": [0.29, 0.71]},
    ]
    assert layout_ranges.read(clip) == payload["ranges"]


def test_split_ranges_in_split_and_remap():
    ranges = [
        {"start": 0.0, "end": 8.0, "layout": "track"},
        {"start": 8.0, "end": 20.0, "layout": "split"},
        {"start": 20.0, "end": 30.0, "layout": "general", "content": [0.29, 0.71]},
    ]
    assert layout_ranges.split_ranges(ranges) == [(8.0, 20.0)]
    assert layout_ranges.in_split(7.99, ranges) is False
    assert layout_ranges.in_split(8.0, ranges) is True
    assert layout_ranges.in_split(15.0, ranges) is True
    assert layout_ranges.in_split(20.0, ranges) is False

    # Recut clip to [5.0, 22.0] -> rebased to [0.0, 17.0]
    remapped = layout_ranges.remap(ranges, offset_seconds=5.0, end_seconds=22.0)
    assert remapped == [
        {"start": 0.0, "end": 3.0, "layout": "track"},
        {"start": 3.0, "end": 15.0, "layout": "split"},
        {"start": 15.0, "end": 17.0, "layout": "general", "content": [0.29, 0.71]},
    ]


def test_missing_or_corrupt_sidecar_fails_soft(tmp_path: Path):
    missing = tmp_path / "nope.mp4"
    assert layout_ranges.read(missing) == []
    assert layout_ranges.read_payload(missing) == {"ranges": [], "punch_ins": []}

    corrupt_clip = tmp_path / "bad.mp4"
    layout_ranges.sidecar_path(corrupt_clip).write_text("{not valid json", encoding="utf-8")
    assert layout_ranges.read(corrupt_clip) == []

