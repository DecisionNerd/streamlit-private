"""A deterministic clock for testing time-based eviction without real sleeps.

The sweeper parks in ``FakeClock.sleep``; tests advance virtual time with
``await clock.advance(seconds)``, which wakes any sleeper whose deadline has
passed and yields control so the sweeper runs its next iteration before the
test asserts. No wall-clock time elapses.
"""

from __future__ import annotations

import asyncio


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self._now = start
        self._waiters: list[tuple[float, asyncio.Event]] = []

    def monotonic(self) -> float:
        return self._now

    async def sleep(self, seconds: float) -> None:
        event = asyncio.Event()
        self._waiters.append((self._now + seconds, event))
        await event.wait()

    async def advance(self, seconds: float) -> None:
        """Move time forward, wake due sleepers, and yield so they can run."""
        self._now += seconds
        still_waiting: list[tuple[float, asyncio.Event]] = []
        for wake_at, event in self._waiters:
            if wake_at <= self._now:
                event.set()
            else:
                still_waiting.append((wake_at, event))
        self._waiters = still_waiting
        # Let woken coroutines (the sweeper) run their next iteration. A couple of
        # yields covers the sweeper re-parking in sleep() within the same advance.
        for _ in range(3):
            await asyncio.sleep(0)


class FakeBridge:
    """Stands in for a connection's bridge teardown. Records whether it was
    cancelled (evicted), and can be told to raise to test sweeper resilience."""

    def __init__(self, *, raises: bool = False) -> None:
        self.cancelled = False
        self.calls = 0
        self._raises = raises

    async def evict(self) -> None:
        self.calls += 1
        if self._raises:
            raise RuntimeError("simulated teardown failure")
        self.cancelled = True
