"""Replay the captured bursts through each strategy and tabulate the verdicts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from detector import Config, Frame, detect
from metrics import _tile_means_rgb, decode_rgb

RUNS = Path(__file__).resolve().parent / "runs"
SCENARIOS = ["instant", "delayed", "spinner", "progress", "staged", "infinite"]
STRATEGIES = [
    ("default", Config(strategy="default")),
    ("custom*", Config(strategy="custom", onset=0.3, settle_eps=0.2, settle_k=6)),
    ("strict", Config(strategy="strict")),
]


def load(name: str) -> tuple[list[Frame], int, float]:
    run = RUNS / name
    meta = json.loads((run / "meta.json").read_text())
    frames = []
    for e in meta["frames"]:
        raw = (run / e["file"]).read_bytes()
        feat = _tile_means_rgb(decode_rgb(raw, 256), 16).flatten().tolist()
        fp = hashlib.sha256(raw).hexdigest()
        frames.append(Frame(t=e["t"], feature=feat, fingerprint=fp))
    return frames, meta["pre_frames"], meta["action_t"]


def main() -> None:
    print(f"{'scenario':10} {'strategy':9} {'verdict':9} {'onset':>8} {'settle':>8}")
    print("-" * 50)
    for name in SCENARIOS:
        frames, pre, action_t = load(name)
        for label, cfg in STRATEGIES:
            r = detect(frames, pre, cfg)
            o = f"+{frames[r.onset_index].t - action_t:.2f}s" if r.onset_index is not None else "—"
            s = f"+{frames[r.settle_index].t - action_t:.2f}s" if r.settle_index is not None else "—"
            print(f"{name:10} {label:9} {r.verdict:9} {o:>8} {s:>8}")
        print()


if __name__ == "__main__":
    main()
