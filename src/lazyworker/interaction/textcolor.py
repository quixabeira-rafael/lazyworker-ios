"""Extract the background and text (glyph) colour from a text box.

A readable text box is bimodal: the background is the majority colour and the
glyphs are a minority that contrasts with it. We model the background as the
dominant colour (default, for the common solid background) and read the text
colour from the stroke cores (pixels farthest from the background, which avoids
anti-aliased edge pixels biasing the result). When the background is not solid
(a gradient/photo) we fall back to a per-row local background so the glyphs are
still separable; the background colour is then flagged as non-solid.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from pydantic import BaseModel

QUANT = 16  # colour bucket size for the background mode
SOLID_MIN = 0.5  # modal-bucket fraction at/above which the background counts as solid
MIN_SEPARATION = 40  # min bg<->glyph RGB distance to accept that text is present
GLYPH_FRACTION = 0.5  # a pixel is a glyph if its distance > this * max distance
MULTICOLOUR_MIN = 0.35  # dominant glyph-colour fraction below which the text is multicolour


class ColorReading(BaseModel):
    background: tuple[int, int, int] | None = None
    text: tuple[int, int, int] | None = None
    solid_background: bool = False
    glyph_ratio: float = 0.0
    confidence: float = 0.0
    note: str = "ok"  # ok | no_text | low_contrast | multicolour | gradient_background


Pixel = tuple[int, int, int]


def _sq(a: Pixel, b: Pixel) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def _mean(pixels: list[Pixel]) -> tuple[int, int, int]:
    n = len(pixels)
    r = sum(p[0] for p in pixels)
    g = sum(p[1] for p in pixels)
    b = sum(p[2] for p in pixels)
    return (round(r / n), round(g / n), round(b / n))


def _dominant(pixels: list[Pixel]) -> tuple[tuple[int, int, int], float]:
    """Mean colour of the most common quantized bucket, and that bucket's fraction."""
    counts = Counter((p[0] // QUANT, p[1] // QUANT, p[2] // QUANT) for p in pixels)
    bucket, count = counts.most_common(1)[0]
    members = [p for p in pixels if (p[0] // QUANT, p[1] // QUANT, p[2] // QUANT) == bucket]
    return _mean(members), count / len(pixels)


def _glyphs_against(pixels: list[Pixel], bg: Pixel) -> tuple[list[Pixel], int]:
    dists = [_sq(p, bg) for p in pixels]
    dmax = max(dists)
    if dmax < MIN_SEPARATION**2:
        return [], dmax
    thr = dmax * GLYPH_FRACTION**2
    glyphs = [p for p, d in zip(pixels, dists, strict=False) if d > thr]
    return glyphs, dmax


def _text_from_glyphs(glyphs: list[Pixel]) -> tuple[tuple[int, int, int], float]:
    """Dominant glyph colour and its fraction of all glyph pixels.

    The text is the most common glyph colour, not the farthest from the background:
    a few very-bright stray pixels are farther but not the actual ink. The dominant
    fraction (how much one colour owns the glyphs) drives the multicolour flag —
    robust to stray pixels and anti-aliased edges, which are a scattered minority.
    """
    return _dominant(glyphs)


def read_text_color(image: Any, *, solid_min: float = SOLID_MIN) -> ColorReading:
    """Read background and text colour from a cropped text box (a PIL image)."""
    data = image.convert("RGB").tobytes()
    pixels: list[Pixel] = [(data[i], data[i + 1], data[i + 2]) for i in range(0, len(data), 3)]
    if not pixels:
        return ColorReading(note="no_text")

    bg, solidity = _dominant(pixels)
    solid = solidity >= solid_min

    if solid:
        glyphs, dmax = _glyphs_against(pixels, bg)
    else:
        glyphs, dmax = _glyphs_per_row(image)

    ratio = len(glyphs) / len(pixels)
    if not glyphs or ratio > 0.6:
        # uniform box => no text; some separation but below the readable bar => low contrast.
        note = "no_text" if dmax < (MIN_SEPARATION // 2) ** 2 else "low_contrast"
        return ColorReading(background=bg, solid_background=solid, glyph_ratio=ratio, note=note)

    text, dominant = _text_from_glyphs(glyphs)
    note = "ok"
    confidence = min(1.0, (dmax**0.5) / 180.0) * (solidity if solid else 0.6)
    if dominant < MULTICOLOUR_MIN:
        note = "multicolour"
        confidence *= 0.5
    elif not solid:
        note = "gradient_background"
    return ColorReading(
        background=bg,
        text=text,
        solid_background=solid,
        glyph_ratio=round(ratio, 4),
        confidence=round(confidence, 3),
        note=note,
    )


def _glyphs_per_row(image: Any) -> tuple[list[Pixel], int]:
    """Local background per row (robust to gradients): glyphs are far from their row median."""
    width, height = image.size
    rgb = image.convert("RGB")
    glyphs: list[Pixel] = []
    dmax = 0
    for y in range(height):
        row = [rgb.getpixel((x, y)) for x in range(width)]
        bg = _median_pixel(row)
        dists = [_sq(p, bg) for p in row]
        rmax = max(dists)
        dmax = max(dmax, rmax)
        if rmax < MIN_SEPARATION**2:
            continue
        thr = rmax * GLYPH_FRACTION**2
        glyphs.extend(p for p, d in zip(row, dists, strict=False) if d > thr)
    return glyphs, dmax


def _median_pixel(pixels: list[Pixel]) -> tuple[int, int, int]:
    return (
        sorted(p[0] for p in pixels)[len(pixels) // 2],
        sorted(p[1] for p in pixels)[len(pixels) // 2],
        sorted(p[2] for p in pixels)[len(pixels) // 2],
    )
