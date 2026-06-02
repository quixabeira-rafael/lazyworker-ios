from __future__ import annotations

import contextlib
from collections.abc import Callable

import pytest

from lazyworker.interaction.models import SettleStrategy, WaitMode
from lazyworker.interaction.wait import (
    WaitSpec,
    _env_float,
    color_distance,
    color_signature,
    settle_wait,
)

Frame = tuple[tuple[int, ...], str]

GRAY: tuple[int, ...] = (128, 128, 128)
GREEN: tuple[int, ...] = (60, 200, 90)


class FakeClock:
    """Time only advances when the detector sleeps -> deterministic, bounded."""

    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, dt: float) -> None:
        self.t += dt


def static(feature: tuple[int, ...], n: int, tag: str) -> list[Frame]:
    return [(feature, tag) for _ in range(n)]


def churn(feature: tuple[int, ...], n: int, tag: str) -> list[Frame]:
    """Sub-onset wobble (one channel +1) with a fresh fingerprint every frame."""
    wobble = (feature[0], feature[1], feature[2] + 1)
    return [((feature if i % 2 else wobble), f"{tag}-{i}") for i in range(n)]


def source(frames: list[Frame]) -> Callable[[], Frame]:
    it = iter(frames)
    last = frames[-1]

    def observe() -> Frame:
        nonlocal last
        with contextlib.suppress(StopIteration):
            last = next(it)
        return last

    return observe


def spec(
    strategy: SettleStrategy, *, timeout: float = 10.0, settle: int = 4, threshold=None
) -> WaitSpec:
    return WaitSpec(
        mode=WaitMode.SETTLE, strategy=strategy, threshold=threshold,
        timeout=timeout, interval=0.4, settle=settle,
    )


STRATEGIES = [SettleStrategy.MAGNITUDE, SettleStrategy.STRICT]


# --- the colour metric sees an equiluminant change grayscale would miss ------

def test_color_distance_detects_equiluminant_change():
    # gray and a green of similar luminance still differ strongly in RGB
    assert color_distance(GRAY, GREEN) > 1.0


def test_env_float_override_and_fallback(monkeypatch):
    monkeypatch.setenv("LAZYWORKER_SETTLE_ONSET", "2.5")
    assert _env_float("LAZYWORKER_SETTLE_ONSET", 1.0) == 2.5
    monkeypatch.setenv("LAZYWORKER_SETTLE_ONSET", "not-a-number")
    assert _env_float("LAZYWORKER_SETTLE_ONSET", 1.0) == 1.0  # invalid -> fallback
    monkeypatch.delenv("LAZYWORKER_SETTLE_ONSET")
    assert _env_float("LAZYWORKER_SETTLE_ONSET", 1.0) == 1.0  # unset -> fallback


def test_color_signature_is_per_tile_rgb():
    Image = pytest.importorskip("PIL.Image")
    import io

    buf = io.BytesIO()
    Image.new("RGB", (200, 400), (10, 20, 30)).save(buf, format="PNG")
    sig = color_signature(buf.getvalue())
    assert len(sig) == 16 * 16 * 3  # SETTLE_GRID tiles, 3 channels
    assert set(sig) == {10, 20, 30}  # a flat image collapses to its colour


# --- instant: change then static -> settles ----------------------------------

@pytest.mark.parametrize("strategy", STRATEGIES)
def test_instant_settles(strategy):
    frames = static(GREEN, 8, "g")
    clk = FakeClock()
    out = settle_wait(source(frames), (GRAY, "base"), spec=spec(strategy),
                      sleep=clk.sleep, clock=clk.now)
    assert out.verdict == "settled" and out.settled and not out.timed_out


# --- delayed: long static gap then a late change -----------------------------

@pytest.mark.parametrize("strategy", STRATEGIES)
def test_delayed_does_not_onset_during_static_gap(strategy):
    frames = static(GRAY, 10, "base") + static(GREEN, 8, "g")
    clk = FakeClock()
    out = settle_wait(source(frames), (GRAY, "base"), spec=spec(strategy),
                      sleep=clk.sleep, clock=clk.now)
    assert out.verdict == "settled" and out.onset


# --- animation: churns sub-onset, then content swaps in and settles ----------

@pytest.mark.parametrize("strategy", STRATEGIES)
def test_animation_waits_through_churn_then_settles(strategy):
    frames = churn(GRAY, 6, "spin") + static(GREEN, 8, "g")
    clk = FakeClock()
    out = settle_wait(source(frames), (GRAY, "base"), spec=spec(strategy),
                      sleep=clk.sleep, clock=clk.now)
    assert out.verdict == "settled" and out.settled


# --- infinite: perpetual sub-onset churn -> busy, never hangs ----------------

@pytest.mark.parametrize("strategy", STRATEGIES)
def test_infinite_is_busy_and_terminates(strategy):
    frames = churn(GRAY, 10_000, "perp")
    clk = FakeClock()
    out = settle_wait(source(frames), (GRAY, "base"), spec=spec(strategy, timeout=2.0),
                      sleep=clk.sleep, clock=clk.now)
    assert out.timed_out and out.verdict == "busy"
    assert out.attempts <= int(2.0 / 0.4) + 1  # bounded by the deadline
    assert clk.now() <= 2.0 + 0.4


# --- truly static: no change at all ------------------------------------------

@pytest.mark.parametrize("strategy", STRATEGIES)
def test_no_change_when_screen_never_moves(strategy):
    frames = static(GRAY, 10_000, "base")
    clk = FakeClock()
    out = settle_wait(source(frames), (GRAY, "base"), spec=spec(strategy, timeout=2.0),
                      sleep=clk.sleep, clock=clk.now)
    assert out.timed_out and out.verdict == "no_change" and not out.onset


# --- custom posture: a higher threshold suppresses a small change ------------

def test_custom_threshold_suppresses_small_change():
    small = (GRAY[0], GRAY[1], GRAY[2] + 3)  # distance = 1.0
    frames = static(small, 8, "s")
    clk = FakeClock()
    loose = settle_wait(source(frames), (GRAY, "base"),
                        spec=spec(SettleStrategy.MAGNITUDE, timeout=2.0),
                        sleep=clk.sleep, clock=clk.now)
    assert loose.verdict in ("settled", "no_change")  # delta 1.0 not > magnitude onset 1.0
    clk2 = FakeClock()
    tight = settle_wait(source(static(small, 8, "s")), (GRAY, "base"),
                        spec=spec(SettleStrategy.CUSTOM, threshold=0.5),
                        sleep=clk2.sleep, clock=clk2.now)
    assert tight.onset and tight.verdict == "settled"
