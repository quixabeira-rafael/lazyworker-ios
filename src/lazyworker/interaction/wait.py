from __future__ import annotations

import hashlib
import io
import operator
import time
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel

from lazyworker.interaction.locator import Locator
from lazyworker.interaction.models import SettleStrategy, WaitMode
from lazyworker.wda.models import AccessibilityNode

DEFAULT_TIMEOUT = 5.0
DEFAULT_INTERVAL = 0.4
DEFAULT_SETTLE = 2

STATUS_BAR_FRACTION = 0.06  # crop the top band (clock/battery) before comparing

# Settle detection: per-tile mean RGB on a small grid (sees equiluminant colour
# changes that grayscale misses), plus exact-identity for the threshold-free path.
SETTLE_GRID = 16
SETTLE_ONSET = 1.0  # magnitude postures: mean per-tile colour delta to count as "moved"
SETTLE_EPS_FRACTION = 0.5  # quiet threshold = onset * this (hysteresis)
STRICT_ONSET_FLOOR = 0.5  # strict onset never drops below this (clean render => sigma 0)
STRICT_BUSY_RATIO = 0.5  # fraction of churning frames (no onset) that reads as "busy"


class WaitUnavailable(Exception):
    """Raised when screenshot diffing is requested but Pillow is not installed."""


class WaitSpec(BaseModel):
    mode: WaitMode
    timeout: float = DEFAULT_TIMEOUT
    interval: float = DEFAULT_INTERVAL
    settle: int = DEFAULT_SETTLE
    locator: Locator | None = None  # required for UNTIL / GONE
    strategy: SettleStrategy = SettleStrategy.STRICT  # SETTLE only; strict is the default posture
    threshold: float | None = None  # SETTLE custom posture: onset delta


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


def color_signature(png: bytes) -> tuple[int, ...]:
    """Per-tile mean RGB on a small grid (status bar cropped) for settle detection."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise WaitUnavailable(
            "settle detection needs Pillow; install it with: pip install 'lazyworker[ocr]'"
        ) from exc

    image = Image.open(io.BytesIO(png)).convert("RGB")
    width, height = image.size
    image = image.crop((0, int(height * STATUS_BAR_FRACTION), width, height)).resize(
        (SETTLE_GRID, SETTLE_GRID), Image.BOX
    )
    return tuple(image.tobytes())


def color_distance(a: tuple[int, ...], b: tuple[int, ...]) -> float:
    """Mean absolute per-channel difference between two colour signatures (0..255)."""
    if not a or not b:
        return 0.0
    return sum(abs(x - y) for x, y in zip(a, b, strict=False)) / len(a)


def fingerprint(png: bytes) -> str:
    """Exact hash of raw screenshot bytes; identical frames => the screen did not move."""
    return hashlib.sha1(png).hexdigest()


class SettleOutcome(BaseModel):
    verdict: str  # settled | busy | no_change
    onset: bool
    settled: bool
    timed_out: bool
    attempts: int
    elapsed_s: float


def settle_wait(
    observe: Callable[[], tuple[tuple[int, ...], str]],
    baseline: tuple[tuple[int, ...], str],
    *,
    spec: WaitSpec,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> SettleOutcome:
    """Stream frames after an action until the screen settles OR the deadline.

    Onset = the screen moved past ``onset``; settle = it then held still for
    ``spec.settle`` reads. STRICT holds via exact frame identity and reports a
    perpetual animation as ``busy``. The deadline guarantees this always returns.
    """
    onset_thr, eps = _settle_thresholds(spec)
    start = clock()
    deadline = start + spec.timeout
    prev_feat, prev_fp = baseline
    onset = False
    quiet = 0
    identical = 0
    churned = 0
    seen = 0
    while True:
        if clock() >= deadline:
            busy = onset or (seen >= 2 and churned / (seen - 1) >= STRICT_BUSY_RATIO)
            verdict = "busy" if busy else "no_change"
            return SettleOutcome(
                verdict=verdict, onset=onset, settled=False, timed_out=True,
                attempts=seen, elapsed_s=round(clock() - start, 3),
            )
        feat, fp = observe()
        seen += 1
        delta = color_distance(prev_feat, feat)
        same = fp == prev_fp
        if not same:
            churned += 1
        if not onset:
            onset = delta > onset_thr
        elif spec.strategy == SettleStrategy.STRICT:
            identical = identical + 1 if same else 0
            if identical >= spec.settle:
                return _settled(start, clock(), seen)
        else:
            quiet = quiet + 1 if delta <= eps else 0
            if quiet >= spec.settle:
                return _settled(start, clock(), seen)
        prev_feat, prev_fp = feat, fp
        sleep(spec.interval)


def _settle_thresholds(spec: WaitSpec) -> tuple[float, float]:
    if spec.strategy == SettleStrategy.STRICT:
        return STRICT_ONSET_FLOOR, 0.0
    onset = spec.threshold if spec.threshold is not None else SETTLE_ONSET
    return onset, onset * SETTLE_EPS_FRACTION


def _settled(start: float, now: float, seen: int) -> SettleOutcome:
    return SettleOutcome(
        verdict="settled", onset=True, settled=True, timed_out=False,
        attempts=seen, elapsed_s=round(now - start, 3),
    )
