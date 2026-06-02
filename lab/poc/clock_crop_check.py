"""Live check: the dynamic status-bar crop neutralises the status-bar clock.

Captures a screenshot, waits past a minute boundary so the status-bar clock
ticks, captures again, and compares the two frames both with and without the
per-device crop. Expectation:

  - uncropped: the frames DIFFER (proves the clock actually changed),
  - cropped  : the frames are IDENTICAL (proves the crop removes the clock).

Run with the project venv (has lazyworker + Pillow) against a booted WDA with a
session open on a static screen, e.g.:

    lazyworker ui open com.lazyworker.lab
    .venv/bin/python lab/poc/clock_crop_check.py
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from lazyworker.interaction.wait import frame_features
from lazyworker.wda.client import WdaClient
from lazyworker.wda.session import Session

STATE = Path(__file__).resolve().parents[2] / ".lazyworker"
WAIT_SECONDS = 65  # any window > 60s crosses at least one minute boundary


def main() -> int:
    run = json.loads((STATE / "run.json").read_text())
    sess = json.loads((STATE / "session.json").read_text())
    s = Session(WdaClient(run["base_url"]), sess["session_id"])

    info = s.screen_info()
    crop = round(info["statusBarSize"]["height"] * info["scale"])
    print(f"device status bar: {info['statusBarSize']['height']}pt x scale {info['scale']} "
          f"=> crop_top = {crop}px")

    a = s.screenshot()
    print(f"captured frame A; waiting {WAIT_SECONDS}s for the clock to tick...")
    time.sleep(WAIT_SECONDS)
    b = s.screenshot()

    raw_a, raw_b = frame_features(a, 0), frame_features(b, 0)
    crop_a, crop_b = frame_features(a, crop), frame_features(b, crop)
    clock_changed = raw_a != raw_b
    crop_identical = crop_a == crop_b

    print(f"uncropped frames differ (clock ticked): {clock_changed}")
    print(f"cropped frames identical (clock removed): {crop_identical}")

    if clock_changed and crop_identical:
        print("PASS: the status-bar clock changed and the crop neutralised it.")
        return 0
    if not clock_changed:
        print("INCONCLUSIVE: the clock did not change (is the screen truly static / "
              "did a minute boundary pass?).")
        return 2
    print("FAIL: the crop did not neutralise the status-bar change.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
