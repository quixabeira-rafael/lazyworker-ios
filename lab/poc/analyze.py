"""POC step 3: turn a captured burst into d(t), detect onset + settle, cost it.

Reads a run produced by burst.py, computes the frame-to-frame distance signal
for each candidate metric, estimates the noise floor from the static pre-frames,
and applies an onset+settle detector: wait for the first real change, then wait
for k consecutive near-zero deltas (the steady state).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from metrics import METRICS, decode_gray

RUNS_DIR = Path(__file__).resolve().parent / "runs"

DECODE_SIZE = 256       # downscale for analysis (keeps cost flat, layout intact)
SETTLE_K = 4            # consecutive sub-threshold deltas required to call "stable"
NOISE_MARGIN = 4.0      # onset/settle threshold = noise_floor * margin (min abs floor)


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "tap_comecar"
    run = RUNS_DIR / name
    meta = json.loads((run / "meta.json").read_text())
    pre = meta["pre_frames"]
    action_t = meta["action_t"]
    entries = meta["frames"]

    t0 = time.monotonic()
    grays = [decode_gray((run / e["file"]).read_bytes(), size=DECODE_SIZE) for e in entries]
    decode_ms = (time.monotonic() - t0) * 1000 / len(grays)
    times = [e["t"] for e in entries]

    print(f"run: {name}   frames: {len(grays)}   pre: {pre}   action_t: {action_t:.3f}s")
    print(f"decode (downscaled {DECODE_SIZE}px): {decode_ms:.1f} ms/frame\n")

    for mname, fn in METRICS.items():
        t0 = time.monotonic()
        d = [0.0] + [fn(grays[i - 1], grays[i]) for i in range(1, len(grays))]
        cost_ms = (time.monotonic() - t0) * 1000 / (len(grays) - 1)

        noise = max(d[1:pre]) if pre > 1 else 0.0
        thresh = max(noise * NOISE_MARGIN, _abs_floor(mname))
        onset, settle = _detect(d, times, pre, thresh)

        print(f"--- {mname:9}  cost={cost_ms:5.2f} ms/frame  noise_floor={noise:7.3f}  thresh={thresh:7.3f}")
        if onset is None:
            print("    onset: NONE (no change detected after action)")
        else:
            oi, ot = onset
            print(f"    onset : frame {oi:3d}  t={ot:.3f}s  (+{ot-action_t:.3f}s after action)")
        if settle is None:
            print("    settle: NONE (never stabilized within window)")
        else:
            si, st = settle
            print(f"    settle: frame {si:3d}  t={st:.3f}s  (+{st-action_t:.3f}s after action)")
        print(f"    d(t) post-action peak={max(d[pre:]):7.3f}  tail(last 4)={_fmt(d[-4:])}\n")


def _detect(d, times, pre, thresh):
    onset = None
    for i in range(pre, len(d)):
        if d[i] > thresh:
            onset = (i, times[i])
            break
    if onset is None:
        return None, None
    run_len = 0
    for i in range(onset[0] + 1, len(d)):
        if d[i] <= thresh:
            run_len += 1
            if run_len >= SETTLE_K:
                j = i - SETTLE_K + 1
                return onset, (j, times[j])
        else:
            run_len = 0
    return onset, None


def _abs_floor(metric: str) -> float:
    return {"tile_mad": 1.0, "full_mad": 1.0, "hist_l1": 0.02, "ssim": 0.002}[metric]


def _fmt(xs) -> str:
    return "[" + ", ".join(f"{x:.3f}" for x in xs) + "]"


if __name__ == "__main__":
    main()
