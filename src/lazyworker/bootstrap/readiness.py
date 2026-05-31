from __future__ import annotations

import time
from collections.abc import Callable


def wait_until_ready(
    probe: Callable[[], bool],
    *,
    timeout: float,
    interval: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> bool:
    """Poll ``probe`` until it returns ``True`` or ``timeout`` elapses.

    ``probe`` must not raise; it should return ``False`` while not ready.
    """
    deadline = clock() + timeout
    while True:
        if probe():
            return True
        if clock() >= deadline:
            return False
        sleep(interval)
