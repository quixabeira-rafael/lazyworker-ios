"""POC step 2: capture a burst of frames around a real action.

Captures a few static pre-frames (to establish the noise floor), fires a tap,
then captures frames as fast as possible for a fixed window. Frames are only
stored as raw PNG + monotonic timestamp here; all distance math happens offline
in analyze.py so the capture loop samples the transition at maximum rate.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from wda import Wda, load_runtime

PRE_FRAMES = 6
POST_SECONDS = 3.5
RUNS_DIR = Path(__file__).resolve().parent / "runs"


def main() -> None:
    if len(sys.argv) != 4:
        print("usage: burst.py <tap_x> <tap_y> <run_name>", file=sys.stderr)
        raise SystemExit(2)
    tap_x, tap_y, name = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    out = RUNS_DIR / name
    out.mkdir(parents=True, exist_ok=True)

    base_url, sid = load_runtime()
    wda = Wda(base_url, sid)
    frames: list[tuple[float, str]] = []
    action_t: float | None = None
    try:
        wda.screenshot()  # warm up
        t_start = time.monotonic()

        for i in range(PRE_FRAMES):
            png = wda.screenshot()
            ts = time.monotonic() - t_start
            _save(out, i, png)
            frames.append((ts, f"{i:04d}.png"))

        action_t = time.monotonic() - t_start
        wda.tap(tap_x, tap_y)

        i = PRE_FRAMES
        while (time.monotonic() - t_start) - action_t < POST_SECONDS:
            png = wda.screenshot()
            ts = time.monotonic() - t_start
            _save(out, i, png)
            frames.append((ts, f"{i:04d}.png"))
            i += 1
    finally:
        wda.close()

    meta = {
        "tap": [tap_x, tap_y],
        "pre_frames": PRE_FRAMES,
        "action_t": action_t,
        "frames": [{"t": t, "file": f} for t, f in frames],
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"captured {len(frames)} frames -> {out}")
    print(f"action fired at t={action_t:.3f}s (after {PRE_FRAMES} pre-frames)")
    span = frames[-1][0] - frames[PRE_FRAMES][0]
    post = len(frames) - PRE_FRAMES
    print(f"post-action: {post} frames in {span:.2f}s  => {post/span:.1f} fps")


def _save(out: Path, i: int, png: bytes) -> None:
    (out / f"{i:04d}.png").write_bytes(png)


if __name__ == "__main__":
    main()
