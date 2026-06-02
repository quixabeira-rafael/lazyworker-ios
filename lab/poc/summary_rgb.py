"""RGB re-analysis of the captured bursts: tile_mad_rgb d(t), onset/settle, shape."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from metrics import decode_rgb, tile_mad_rgb

RUNS = Path(__file__).resolve().parent / "runs"
SETTLE_K = 4
NOISE_MARGIN = 4.0
ABS_FLOOR = 1.0
BLOCKS = " ▁▂▃▄▅▆▇█"


def spark(values: list[float], peak: float) -> str:
    if peak <= 0:
        return BLOCKS[0] * len(values)
    return "".join(
        BLOCKS[min(len(BLOCKS) - 1, int(round(v / peak * (len(BLOCKS) - 1))))]
        for v in values
    )


def analyze(name: str) -> None:
    run = RUNS / name
    meta = json.loads((run / "meta.json").read_text())
    pre = meta["pre_frames"]
    action_t = meta["action_t"]
    entries = meta["frames"]
    frames = [decode_rgb((run / e["file"]).read_bytes(), size=256) for e in entries]
    times = [e["t"] for e in entries]
    d = [0.0] + [tile_mad_rgb(frames[i - 1], frames[i]) for i in range(1, len(frames))]

    noise = max(d[1:pre]) if pre > 1 else 0.0
    thresh = max(noise * NOISE_MARGIN, ABS_FLOOR)

    onset = next((i for i in range(pre, len(d)) if d[i] > thresh), None)
    settle = None
    if onset is not None:
        runlen = 0
        for i in range(onset + 1, len(d)):
            if d[i] <= thresh:
                runlen += 1
                if runlen >= SETTLE_K:
                    settle = i - SETTLE_K + 1
                    break
            else:
                runlen = 0

    post = d[pre:]
    o_s = f"+{times[onset]-action_t:.2f}s (f{onset})" if onset is not None else "—"
    s_s = f"+{times[settle]-action_t:.2f}s (f{settle})" if settle is not None else "NEVER (timeout)"
    print(f"== {name}")
    print(f"   noise={noise:.2f} thresh={thresh:.2f} peak={max(post):.1f}")
    print(f"   onset {o_s}   settle {s_s}")
    print(f"   d(t) post |{spark(post, max(post))}|")


if __name__ == "__main__":
    names = sys.argv[1:] or [
        "instant", "delayed", "spinner", "progress", "staged", "infinite",
    ]
    for n in names:
        analyze(n)
        print()
