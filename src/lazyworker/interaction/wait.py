from __future__ import annotations

import hashlib
import io
import operator
import time
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel

from lazyworker.interaction.locator import Locator
from lazyworker.interaction.models import WaitMode
from lazyworker.wda.models import AccessibilityNode

DEFAULT_TIMEOUT = 5.0
DEFAULT_INTERVAL = 0.4
DEFAULT_SETTLE = 2

# Screenshot diff: count grayscale pixels that differ on a 64x64 downsample.
SCREEN_GRID = 64
SCREEN_PIXEL_DELTA = 16  # per-pixel grayscale delta (0-255) to count as different
SCREEN_CHANGED_PIXELS = 12  # >= this many changed pixels => the screen changed
SCREEN_STABLE_PIXELS = 3  # <= this many => the screen is stable
STATUS_BAR_FRACTION = 0.06  # crop the top band (clock/battery) before comparing


class WaitUnavailable(Exception):
    """Raised when screenshot diffing is requested but Pillow is not installed."""


class WaitSpec(BaseModel):
    mode: WaitMode
    timeout: float = DEFAULT_TIMEOUT
    interval: float = DEFAULT_INTERVAL
    settle: int = DEFAULT_SETTLE
    locator: Locator | None = None  # required for UNTIL / GONE


S = TypeVar("S")


def wait_for(
    observe: Callable[[], S],
    accept: Callable[[S], bool],
    *,
    timeout: float,
    interval: float,
    settle: int,
    same: Callable[[S, S], bool] = operator.eq,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[bool, bool, bool, int, float]:
    """Poll until ``accept`` holds AND the observation has been stable for ``settle`` reads.

    Returns (ok, satisfied, settled, attempts, elapsed_s). Deterministic given the
    injected ``observe``/``sleep``/``clock``.
    """
    start = clock()
    deadline = start + timeout
    prev: S | None = None
    stable = 0
    attempts = 0
    while True:
        cur = observe()
        attempts += 1
        if prev is not None and same(prev, cur):
            stable += 1
        else:
            stable = 1
        satisfied = accept(cur)
        settled = stable >= settle
        if (satisfied and settled) or clock() >= deadline:
            return satisfied and settled, satisfied, settled, attempts, clock() - start
        prev = cur
        sleep(interval)


def tree_signature(node: AccessibilityNode) -> str:
    """Structural hash of the visible tree (type/identifier/label/value), ignoring frames."""
    parts: list[str] = []
    for element in node.walk():
        if element.visible is False:
            continue
        parts.append(
            f"{element.type}|{element.identifier or ''}|{element.label or ''}|{element.value or ''}"
        )
    return hashlib.sha1("\n".join(parts).encode()).hexdigest()


def image_signature(png: bytes) -> tuple[int, ...]:
    """Downsampled grayscale pixels (status bar cropped) for screenshot diffing."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise WaitUnavailable(
            "screenshot diffing needs Pillow; install it with: pip install 'lazyworker[ocr]'"
        ) from exc

    image = Image.open(io.BytesIO(png)).convert("L")
    width, height = image.size
    image = image.crop((0, int(height * STATUS_BAR_FRACTION), width, height)).resize(
        (SCREEN_GRID, SCREEN_GRID)
    )
    return tuple(image.getdata())


def image_distance(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    """Number of pixels that differ by more than the per-pixel delta."""
    return sum(1 for x, y in zip(a, b, strict=False) if abs(x - y) > SCREEN_PIXEL_DELTA)
