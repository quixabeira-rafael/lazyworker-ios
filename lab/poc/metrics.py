"""Frame-to-frame distance metrics for steady-state detection.

Each metric maps a pair of decoded frames to a scalar distance. The goal is to
turn a stream of screenshots into a 1D signal d(t) whose value is high during
transitions/animations and near zero when the UI is stable.
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image

STATUS_BAR_FRACTION = 0.06  # crop the top strip (clock/battery flicker) like wait.py


def decode_gray(png: bytes, size: int | None = None) -> np.ndarray:
    """PNG bytes -> 2D grayscale float array, status bar cropped, optionally resized."""
    image = Image.open(io.BytesIO(png)).convert("L")
    w, h = image.size
    image = image.crop((0, int(h * STATUS_BAR_FRACTION), w, h))
    if size is not None:
        image = image.resize((size, size))
    return np.asarray(image, dtype=np.float32)


def decode_rgb(png: bytes, size: int | None = None) -> np.ndarray:
    image = Image.open(io.BytesIO(png)).convert("RGB")
    w, h = image.size
    image = image.crop((0, int(h * STATUS_BAR_FRACTION), w, h))
    if size is not None:
        image = image.resize((size, size))
    return np.asarray(image, dtype=np.float32)


def tile_mad(a: np.ndarray, b: np.ndarray, tiles: int = 16) -> float:
    """Mean absolute difference of per-tile mean brightness (0..255).

    Cheap and robust to sub-pixel jitter: collapses each frame to a tiles x tiles
    grid of averages before differencing.
    """
    ta = _tile_means(a, tiles)
    tb = _tile_means(b, tiles)
    return float(np.mean(np.abs(ta - tb)))


def tile_mad_rgb(a: np.ndarray, b: np.ndarray, tiles: int = 16) -> float:
    """Per-tile mean colour difference (mean over R,G,B of |Δ| of tile means).

    Same spatial collapse as tile_mad but keeps the three channels, so it sees
    equiluminant colour changes that grayscale misses.
    """
    ta = _tile_means_rgb(a, tiles)
    tb = _tile_means_rgb(b, tiles)
    return float(np.mean(np.abs(ta - tb)))


def full_mad(a: np.ndarray, b: np.ndarray) -> float:
    """Mean absolute difference over every pixel (0..255)."""
    return float(np.mean(np.abs(a - b)))


def hist_l1(a: np.ndarray, b: np.ndarray, bins: int = 64) -> float:
    """L1 distance between normalized grayscale histograms (0..2).

    Ignores spatial layout entirely: only the brightness distribution.
    """
    ha, _ = np.histogram(a, bins=bins, range=(0, 255), density=True)
    hb, _ = np.histogram(b, bins=bins, range=(0, 255), density=True)
    return float(np.sum(np.abs(ha - hb)))


def ssim_distance(a: np.ndarray, b: np.ndarray) -> float:
    """1 - global SSIM (0 = identical, ->1 = very different)."""
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    mu_a, mu_b = a.mean(), b.mean()
    va, vb = a.var(), b.var()
    cov = ((a - mu_a) * (b - mu_b)).mean()
    ssim = ((2 * mu_a * mu_b + c1) * (2 * cov + c2)) / (
        (mu_a**2 + mu_b**2 + c1) * (va + vb + c2)
    )
    return float(1.0 - ssim)


def _tile_means(arr: np.ndarray, tiles: int) -> np.ndarray:
    h, w = arr.shape
    th, tw = h // tiles, w // tiles
    cropped = arr[: th * tiles, : tw * tiles]
    return cropped.reshape(tiles, th, tiles, tw).mean(axis=(1, 3))


def _tile_means_rgb(arr: np.ndarray, tiles: int) -> np.ndarray:
    h, w, c = arr.shape
    th, tw = h // tiles, w // tiles
    cropped = arr[: th * tiles, : tw * tiles]
    return cropped.reshape(tiles, th, tiles, tw, c).mean(axis=(1, 3))


METRICS = {
    "tile_mad": tile_mad,
    "full_mad": full_mad,
    "hist_l1": hist_l1,
    "ssim": ssim_distance,
}
