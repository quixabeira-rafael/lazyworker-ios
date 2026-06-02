"""Deterministic tests for the steady-state detector across the three strategies.

Frames are synthetic: ``feature`` is a 1-D colour vector and ``fingerprint`` is
an exact token we control, so each scenario shape (instant, delayed, animated,
staged, perpetual) is reproduced without a device.
"""
from __future__ import annotations

from detector import Config, Frame, detect, detect_live

PRE = 4


class FakeClock:
    """Deterministic clock: time only advances when the detector sleeps."""

    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, dt: float) -> None:
        self.t += dt


def frame(t: float, color: float, token: str) -> Frame:
    return Frame(t=t, feature=[color, color, color], fingerprint=token)


def static(color: float, n: int, start: int) -> list[Frame]:
    """n byte-identical frames at a fixed colour."""
    return [frame(float(start + i), color, f"c{color}") for i in range(n)]


def churn(color: float, n: int, start: int, tag: str) -> list[Frame]:
    """n frames that move sub-onset (tiny colour jitter) but never repeat (fresh hash)."""
    return [
        frame(float(start + i), color + (i % 2) * 0.1, f"{tag}-{start + i}")
        for i in range(n)
    ]


def stream(*chunks: list[Frame]) -> list[Frame]:
    out: list[Frame] = []
    for chunk in chunks:
        out.extend(chunk)
    return out


STRATEGIES = [Config(strategy="default"), Config(strategy="strict")]


# --- instant: equiluminant colour swap, then static -------------------------

def test_instant_settles_right_after_onset():
    frames = stream(static(100, PRE, 0), static(150, 8, PRE))
    for cfg in STRATEGIES:
        r = detect(frames, PRE, cfg)
        assert r.verdict == "settled", cfg.strategy
        assert r.onset_index == PRE
        assert r.settle_index is not None and r.settle_index >= r.onset_index


# --- delayed: long static gap, then a late change ---------------------------

def test_delayed_does_not_onset_during_static_gap():
    change_at = PRE + 10
    frames = stream(static(100, PRE, 0), static(100, 10, PRE), static(200, 6, change_at))
    for cfg in STRATEGIES:
        r = detect(frames, PRE, cfg)
        assert r.verdict == "settled", cfg.strategy
        assert r.onset_index == change_at, cfg.strategy
        assert r.settle_index is not None and r.settle_index > change_at


# --- animation: churns sub-onset, then content swaps in and settles ---------

def test_animation_waits_through_churn_then_settles():
    swap_at = PRE + 12
    frames = stream(static(100, PRE, 0), churn(100, 12, PRE, "spin"), static(200, 6, swap_at))
    for cfg in STRATEGIES:
        r = detect(frames, PRE, cfg)
        assert r.verdict == "settled", cfg.strategy
        # onset is the real swap, not the sub-onset churn
        assert r.onset_index == swap_at, cfg.strategy
        assert r.settle_index is not None and r.settle_index >= swap_at


# --- staged: discrete changes with quiet gaps (the documented semantic limit)

def test_staged_settles_prematurely_on_first_plateau():
    last_change = PRE + 16
    frames = stream(
        static(100, PRE, 0),
        static(120, 8, PRE),
        static(160, 8, PRE + 8),
        static(220, 6, last_change),
    )
    for cfg in STRATEGIES:
        r = detect(frames, PRE, cfg)
        assert r.verdict == "settled", cfg.strategy
        # visual-only detection cannot know more is coming: it settles before the last change
        assert r.settle_index is not None and r.settle_index < last_change, cfg.strategy


# --- infinite: perpetual sub-onset churn never settles ----------------------

def test_infinite_is_busy_not_settled():
    frames = stream(static(100, PRE, 0), churn(100, 40, PRE, "perp"))
    for cfg in STRATEGIES:
        r = detect(frames, PRE, cfg)
        assert r.verdict == "busy", cfg.strategy
        assert r.settle_index is None


# --- truly static after the action: no change at all ------------------------

def test_no_change_when_screen_never_moves():
    frames = stream(static(100, PRE, 0), static(100, 20, PRE))
    for cfg in STRATEGIES:
        r = detect(frames, PRE, cfg)
        assert r.verdict == "no_change", cfg.strategy
        assert r.onset_index is None


# --- custom posture: a higher onset suppresses a small change ---------------

def test_custom_threshold_suppresses_small_change():
    frames = stream(static(100, PRE, 0), static(101, 8, PRE))  # delta = 1.0
    loose = detect(frames, PRE, Config(strategy="default"))      # onset 1.0 -> not > 1.0
    tight = detect(frames, PRE, Config(strategy="custom", onset=0.5, settle_eps=0.2, settle_k=4))
    assert loose.onset_index is None
    assert tight.onset_index == PRE and tight.verdict == "settled"


# --- strict adaptive onset has an absolute floor (clean screen, sigma=0) -----

def test_strict_onset_floor_rejects_microscopic_jitter():
    # static gray (sigma=0) then a microscopic 0.1 wobble that must NOT trigger onset
    frames = stream(static(100, PRE, 0), churn(100, 10, PRE, "micro"))
    r = detect(frames, PRE, Config(strategy="strict"))
    assert r.onset_index is None
    assert r.verdict == "busy"  # it keeps churning, just below the floor


# --- live mode: the deadline guarantees termination -------------------------

TIMEOUT = 2.0
INTERVAL = 0.4
MAX_POLLS = int(TIMEOUT / INTERVAL) + 1  # the detector cannot poll more than this


def source(frames: list[Frame]) -> "callable":
    it = iter(frames)
    last = frames[-1]

    def nxt() -> Frame:
        nonlocal last
        try:
            last = next(it)
        except StopIteration:
            pass
        return last

    return nxt


def test_live_settles_and_does_not_time_out():
    baseline = static(100, PRE, 0)
    post = stream(churn(100, 2, PRE, "spin"), static(200, 10, PRE + 2))
    clk = FakeClock()
    r = detect_live(
        baseline, source(post), cfg=Config(strategy="strict"),
        timeout=5.0, interval=INTERVAL, sleep=clk.sleep, clock=clk.now,
    )
    assert r.verdict == "settled" and r.settled and not r.timed_out
    assert clk.now() < 5.0  # returned early, well before the deadline


def test_live_infinite_spinner_times_out_as_busy():
    baseline = static(100, PRE, 0)
    # never repeats, sub-onset: would loop forever without a deadline
    forever = churn(100, 10_000, PRE, "perp")
    clk = FakeClock()
    r = detect_live(
        baseline, source(forever), cfg=Config(strategy="strict"),
        timeout=TIMEOUT, interval=INTERVAL, sleep=clk.sleep, clock=clk.now,
    )
    assert r.timed_out and r.verdict == "busy"
    assert r.frames <= MAX_POLLS and clk.now() <= TIMEOUT + INTERVAL


def test_live_change_that_never_arrives_times_out_as_no_change():
    baseline = static(100, PRE, 0)
    forever_static = static(100, 10_000, PRE)
    clk = FakeClock()
    r = detect_live(
        baseline, source(forever_static), cfg=Config(strategy="strict"),
        timeout=TIMEOUT, interval=INTERVAL, sleep=clk.sleep, clock=clk.now,
    )
    assert r.timed_out and r.verdict == "no_change" and not r.onset
    assert r.frames <= MAX_POLLS
