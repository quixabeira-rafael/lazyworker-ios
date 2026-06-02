"""POC step 1: measure screenshot throughput and where the time goes.

Splits each capture into transfer (HTTP GET + base64 decode -> bytes) and
decode (PNG -> grayscale array). Answers: how fast can we sample, how much
jitter, and is the bottleneck I/O or the math.
"""
from __future__ import annotations

import statistics
import time

from metrics import decode_gray
from wda import Wda, load_runtime

N = 40


def main() -> None:
    base_url, sid = load_runtime()
    wda = Wda(base_url, sid)
    transfer, decode, total = [], [], []
    sizes = []
    try:
        wda.screenshot()  # warm up
        for _ in range(N):
            t0 = time.monotonic()
            png = wda.screenshot()
            t1 = time.monotonic()
            decode_gray(png)
            t2 = time.monotonic()
            transfer.append((t1 - t0) * 1000)
            decode.append((t2 - t1) * 1000)
            total.append((t2 - t0) * 1000)
            sizes.append(len(png))
    finally:
        wda.close()

    def stats(xs: list[float]) -> str:
        return (
            f"mean={statistics.mean(xs):6.1f}  min={min(xs):6.1f}  "
            f"max={max(xs):6.1f}  stdev={statistics.pstdev(xs):5.1f}"
        )

    print(f"samples: {N}   png size: {statistics.mean(sizes)/1024:.0f} KB avg")
    print(f"transfer ms : {stats(transfer)}")
    print(f"decode   ms : {stats(decode)}")
    print(f"total    ms : {stats(total)}")
    fps = 1000.0 / statistics.mean(total)
    print(f"\neffective rate: {fps:5.1f} fps   (interval ~{statistics.mean(total):.0f} ms)")
    print(f"jitter (total stdev): {statistics.pstdev(total):.1f} ms")


if __name__ == "__main__":
    main()
