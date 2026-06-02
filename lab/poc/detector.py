"""Steady-state detector POC: three threshold postures over one frame stream.

The detector turns a sequence of frames into an onset+settle decision. A frame
is reduced to two cheap features:

  - ``feature``: per-tile mean RGB (sees equiluminant colour changes),
  - ``fingerprint``: an exact hash of the raw bytes (byte-identical => no change).

``d(t)`` is the mean per-tile colour distance between consecutive features.

Strategies (the "posture", not a magic number the caller has to guess):

  - ``default`` : built-in absolute thresholds; settle = k consecutive deltas <= eps.
  - ``custom``  : same engine, thresholds supplied per call.
  - ``strict``  : onset = adaptive (mean + z*stdev of the static noise floor);
                  settle = k consecutive *byte-identical* frames (no threshold).
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from statistics import mean, pstdev

# Built-in thresholds for the "default" posture (tile_mad_rgb units, 0..255).
DEFAULT_ONSET = 1.0
DEFAULT_SETTLE_EPS = 0.5
DEFAULT_SETTLE_K = 4
STRICT_Z = 6.0
STRICT_IDENTICAL_K = 4
ONSET_FLOOR = 0.5   # adaptive onset can never drop below this (clean screens have sigma=0)
BUSY_RATIO = 0.5    # >= this fraction of post-frames churning, with no onset => busy


@dataclass
class Frame:
    t: float
    feature: list[float]      # flattened per-tile mean RGB
    fingerprint: str          # exact hash of the source bytes


@dataclass
class Config:
    strategy: str = "default"
    onset: float = DEFAULT_ONSET
    settle_eps: float = DEFAULT_SETTLE_EPS
    settle_k: int = DEFAULT_SETTLE_K
    z: float = STRICT_Z
    identical_k: int = STRICT_IDENTICAL_K


@dataclass
class Result:
    onset_index: int | None = None
    settle_index: int | None = None
    verdict: str = "no_change"      # settled | busy | no_change
    deltas: list[float] = field(default_factory=list)
    onset_threshold: float = 0.0


def distance(a: list[float], b: list[float]) -> float:
    return mean(abs(x - y) for x, y in zip(a, b))


def detect(frames: list[Frame], pre: int, cfg: Config) -> Result:
    """Run the onset->settle state machine over an already-captured stream."""
    deltas = [0.0] + [distance(frames[i - 1].feature, frames[i].feature) for i in range(1, len(frames))]
    onset_thr = _onset_threshold(deltas, pre, cfg)
    res = Result(deltas=deltas, onset_threshold=onset_thr)

    onset = next((i for i in range(pre, len(deltas)) if deltas[i] > onset_thr), None)
    if onset is None:
        # Nothing crossed the onset bar. Either truly static, or a perpetual
        # sub-threshold animation. Magnitude can't tell them apart (a tiny spinner
        # barely moves), but exact-identity can: a busy screen keeps producing
        # fresh frames even when each delta is microscopic.
        res.verdict = "busy" if _churn_ratio(frames, pre) >= BUSY_RATIO else "no_change"
        return res
    res.onset_index = onset

    settle = _find_settle(frames, deltas, onset, cfg)
    if settle is None:
        res.verdict = "busy"
        return res
    res.settle_index = settle
    res.verdict = "settled"
    return res


def _onset_threshold(deltas: list[float], pre: int, cfg: Config) -> float:
    if cfg.strategy == "strict":
        noise = deltas[1:pre]
        adaptive = mean(noise) + cfg.z * pstdev(noise) if noise else 0.0
        return max(adaptive, ONSET_FLOOR)
    return cfg.onset


def _find_settle(frames: list[Frame], deltas: list[float], onset: int, cfg: Config) -> int | None:
    if cfg.strategy == "strict":
        run = 0
        for i in range(onset + 1, len(frames)):
            if frames[i].fingerprint == frames[i - 1].fingerprint:
                run += 1
                if run >= cfg.identical_k:
                    return i - cfg.identical_k + 1
            else:
                run = 0
        return None
    run = 0
    for i in range(onset + 1, len(deltas)):
        if deltas[i] <= cfg.settle_eps:
            run += 1
            if run >= cfg.settle_k:
                return i - cfg.settle_k + 1
        else:
            run = 0
    return None


@dataclass
class LiveResult:
    verdict: str          # settled | busy | no_change
    onset: bool
    settled: bool
    timed_out: bool
    frames: int
    elapsed: float


def detect_live(
    baseline: list[Frame],
    next_frame: Callable[[], Frame],
    *,
    cfg: Config,
    timeout: float,
    interval: float,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> LiveResult:
    """Stream frames after an action until settle OR the deadline — never hangs.

    The deadline is the safety valve for the "smart" posture: a perpetual
    animation (busy) or a change that never arrives would otherwise loop forever.
    On timeout it still returns a verdict, derived from what it observed.
    """
    noise = [distance(baseline[i - 1].feature, baseline[i].feature) for i in range(1, len(baseline))]
    onset_thr = _onset_threshold([0.0, *noise], len(baseline), cfg)

    start = clock()
    deadline = start + timeout
    prev = baseline[-1]
    onset = False
    quiet = 0
    identical = 0
    churned = 0
    seen = 0
    while True:
        if clock() >= deadline:
            verdict = "busy" if onset or _churn(churned, seen) >= BUSY_RATIO else "no_change"
            return LiveResult(verdict, onset, False, True, seen, clock() - start)
        cur = next_frame()
        seen += 1
        d = distance(prev.feature, cur.feature)
        same = cur.fingerprint == prev.fingerprint
        if not same:
            churned += 1
        if not onset:
            onset = d > onset_thr
        elif cfg.strategy == "strict":
            identical = identical + 1 if same else 0
            if identical >= cfg.identical_k:
                return LiveResult("settled", True, True, False, seen, clock() - start)
        else:
            quiet = quiet + 1 if d <= cfg.settle_eps else 0
            if quiet >= cfg.settle_k:
                return LiveResult("settled", True, True, False, seen, clock() - start)
        prev = cur
        sleep(interval)


def _churn(changed: int, pairs: int) -> float:
    return changed / pairs if pairs else 0.0


def _churn_ratio(frames: list[Frame], pre: int) -> float:
    """Fraction of post-frames that differ (by exact hash) from the one before."""
    post = frames[pre:]
    if len(post) < 2:
        return 0.0
    changed = sum(1 for i in range(1, len(post)) if post[i].fingerprint != post[i - 1].fingerprint)
    return changed / (len(post) - 1)
