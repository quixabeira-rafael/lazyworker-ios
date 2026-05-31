from __future__ import annotations

from collections.abc import Callable, Sequence

from pydantic import BaseModel


class OcrUnavailable(Exception):
    """Raised when the OCR backend (ocrmac / Apple Vision) is not installed."""


# Engine returns (text, confidence, normalized_box) where the box is
# (x, y, w, h) in [0,1] with a bottom-left origin (Apple Vision's convention).
OcrEngine = Callable[[str], list[tuple[str, float, Sequence[float]]]]


class OcrText(BaseModel):
    """A piece of text recognized from the screenshot pixels, in screen points."""

    text: str
    box: tuple[int, int, int, int]  # x, y, width, height (top-left origin)
    size: tuple[int, int]  # width, height
    confidence: float


def _vision_engine(image_path: str) -> list[tuple[str, float, Sequence[float]]]:
    try:
        from ocrmac import ocrmac
    except ImportError as exc:
        raise OcrUnavailable(
            "OCR backend not installed; install it with: pip install 'lazyworker[ocr]'"
        ) from exc
    annotations = ocrmac.OCR(image_path).recognize()
    return [(str(text), float(conf), tuple(box)) for text, conf, box in annotations]


def recognize(
    image_path: str,
    *,
    screen_width: int,
    screen_height: int,
    engine: OcrEngine | None = None,
) -> list[OcrText]:
    """OCR a screenshot, returning texts in screen-point boxes (top-left origin).

    The engine yields Vision's normalized, bottom-left boxes; we map them onto the
    screen's point frame so OCR boxes line up with accessibility-tree element boxes.
    """
    results: list[OcrText] = []
    for text, confidence, box in (engine or _vision_engine)(image_path):
        nx, ny, nw, nh = box[0], box[1], box[2], box[3]
        x = round(nx * screen_width)
        y = round((1.0 - ny - nh) * screen_height)
        w = round(nw * screen_width)
        h = round(nh * screen_height)
        results.append(
            OcrText(text=text, box=(x, y, w, h), size=(w, h), confidence=round(confidence, 3))
        )
    results.sort(key=lambda item: (item.box[1], item.box[0]))
    return results
