"""Hardware encoder resource governor and VRAM limiter.

Prevents:
- Driver crashes from exceeding NVENC session limits (3 or 5 streams on GeForce)
- GPU VRAM exhaustion under concurrent 4K/2K encoding
Works in both synchronous and asynchronous contexts without socket dependence.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


class _SlotContext:
    def __init__(self, gov: NvencGovernor, slots: int, height: int) -> None:
        self.gov = gov
        self.slots = slots
        self.height = height

    def __enter__(self) -> _SlotContext:
        self.gov._acquire_slots(self.slots, self.height)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.gov._release_slots(self.slots)

    async def __aenter__(self) -> _SlotContext:
        self.gov._acquire_slots(self.slots, self.height)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.gov._release_slots(self.slots)


class NvencGovernor:
    """Weighted slot limiter for hardware video encoding."""

    def __init__(self, total_slots: int = 3, min_vram_mb_4k: int = 1500) -> None:
        self.total_slots = total_slots
        self.min_vram_mb_4k = min_vram_mb_4k
        self._available_slots = total_slots
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)

    @staticmethod
    def get_free_vram_mb() -> int | None:
        """Query free GPU VRAM via nvidia-smi."""
        try:
            cmd = [
                "nvidia-smi",
                "--query-gpu=memory.free",
                "--format=csv,noheader,nounits",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
            if res.returncode == 0 and res.stdout.strip():
                lines = res.stdout.strip().splitlines()
                return int(lines[0].strip())
        except Exception as exc:
            logger.debug("nvidia-smi query unavailable: %s", exc)
        return None

    def _acquire_slots(self, slots_needed: int, height: int) -> None:
        with self._condition:
            while self._available_slots < slots_needed:
                self._condition.wait()

            # Pre-flight VRAM verification for 4K
            if height >= 2160:
                free_mb = self.get_free_vram_mb()
                if free_mb is not None and free_mb < self.min_vram_mb_4k:
                    logger.warning(
                        "Low VRAM for 4K NVENC encode (%d MB free < %d MB required). Queuing...",
                        free_mb,
                        self.min_vram_mb_4k,
                    )
                    time.sleep(1.0)

            self._available_slots -= slots_needed
            logger.info("NVENC acquired %d slots (remaining: %d)", slots_needed, self._available_slots)

    def _release_slots(self, slots_needed: int) -> None:
        with self._condition:
            self._available_slots += slots_needed
            logger.info("NVENC released %d slots (remaining: %d)", slots_needed, self._available_slots)
            self._condition.notify_all()

    def acquire(self, height: int) -> _SlotContext:
        """Acquire required encoder slots based on resolution. Supports 'with' and 'async with'."""
        # 4K consumes all 3 slots (serialized), 1440p=2 slots, 1080p=1 slot
        if height >= 2160:
            slots_needed = 3
        elif height >= 1440:
            slots_needed = 2
        else:
            slots_needed = 1

        slots_needed = min(slots_needed, self.total_slots)
        return _SlotContext(self, slots_needed, height)


# Global singleton governor
GLOBAL_NVENC_GOVERNOR = NvencGovernor()
