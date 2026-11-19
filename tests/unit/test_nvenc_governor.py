"""Unit tests for lib/nvenc_governor.py."""

from __future__ import annotations

import threading
from lib.nvenc_governor import NvencGovernor


def test_nvenc_governor_slot_allocation_sync():
    gov = NvencGovernor(total_slots=3)

    # 1080p takes 1 slot
    with gov.acquire(1080):
        assert gov._available_slots == 2

        # 1440p takes 2 slots
        with gov.acquire(1440):
            assert gov._available_slots == 0

    assert gov._available_slots == 3


def test_nvenc_governor_4k_serialization_sync():
    gov = NvencGovernor(total_slots=3)

    # 4K takes all 3 slots
    with gov.acquire(2160):
        assert gov._available_slots == 0

    assert gov._available_slots == 3


def test_nvenc_governor_threaded_concurrency():
    gov = NvencGovernor(total_slots=3)
    results = []

    def worker(height: int, label: str):
        with gov.acquire(height):
            results.append(f"{label}_start")
            assert gov._available_slots >= 0
            results.append(f"{label}_end")

    t1 = threading.Thread(target=worker, args=(1080, "w1"))
    t2 = threading.Thread(target=worker, args=(1440, "w2"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert gov._available_slots == 3
    assert len(results) == 4
