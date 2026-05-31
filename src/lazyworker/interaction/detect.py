from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from pydantic import BaseModel


class DetectorUnavailable(Exception):
    """Raised when the local visual detector (OmniParser) is not installed."""


# Engine returns (label, confidence, normalized_box) where the box is
# (x, y, w, h) in [0,1] with a top-left origin, relative to the image.
DetectEngine = Callable[[str], list[tuple[str, float, Sequence[float]]]]

DEFAULT_MIN_CONFIDENCE = 0.3


class DetectedElement(BaseModel):
    """A UI element detected from screenshot pixels (icons/buttons/regions)."""

    label: str
    box: tuple[int, int, int, int]  # x, y, width, height (screen points)
    size: tuple[int, int]
    confidence: float
    container: str | None = None


def detect(
    image_path: str,
    *,
    screen_width: int,
    screen_height: int,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    engine: DetectEngine | None = None,
) -> list[DetectedElement]:
    """Run a visual UI detector, returning elements in screen-point boxes.

    The engine yields normalized top-left boxes; we map them onto the screen's
    point frame so detections line up with accessibility-tree and OCR boxes.
    """
    results: list[DetectedElement] = []
    for label, confidence, box in (engine or _omniparser_engine)(image_path):
        if confidence < min_confidence:
            continue
        nx, ny, nw, nh = box[0], box[1], box[2], box[3]
        x = round(nx * screen_width)
        y = round(ny * screen_height)
        w = round(nw * screen_width)
        h = round(nh * screen_height)
        results.append(
            DetectedElement(
                label=label, box=(x, y, w, h), size=(w, h), confidence=round(confidence, 3)
            )
        )
    results.sort(key=lambda item: (item.box[1], item.box[0]))
    return results


_MODELS: tuple[Any, Any, Any] | None = None


def _load_models() -> tuple[Any, Any, Any]:
    global _MODELS
    if _MODELS is not None:
        return _MODELS
    try:
        import torch
        from huggingface_hub import hf_hub_download, snapshot_download
        from transformers import AutoModelForCausalLM, AutoProcessor
        from ultralytics import YOLO
    except ImportError as exc:
        raise DetectorUnavailable(
            "visual detector not installed; install it with: pip install 'lazyworker[detect]'"
        ) from exc

    import os

    yolo = YOLO(hf_hub_download("microsoft/OmniParser-v2.0", "icon_detect/model.pt"))
    caption_dir = os.path.join(
        snapshot_download("microsoft/OmniParser-v2.0", allow_patterns=["icon_caption/*"]),
        "icon_caption",
    )
    caption_model = AutoModelForCausalLM.from_pretrained(
        caption_dir, trust_remote_code=True, torch_dtype=torch.float32
    )
    caption_processor = AutoProcessor.from_pretrained(
        "microsoft/Florence-2-base-ft", trust_remote_code=True
    )
    _MODELS = (yolo, caption_model, caption_processor)
    return _MODELS


def _omniparser_engine(image_path: str) -> list[tuple[str, float, Sequence[float]]]:
    from PIL import Image

    yolo, caption_model, caption_processor = _load_models()
    detections = yolo.predict(image_path, conf=0.05, verbose=False)[0]
    image = Image.open(image_path).convert("RGB")
    width, height = image.size

    out: list[tuple[str, float, Sequence[float]]] = []
    for box in detections.boxes:
        x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
        confidence = float(box.conf[0])
        crop = image.crop((x1, y1, x2, y2))
        inputs = caption_processor(text="<CAPTION>", images=crop, return_tensors="pt")
        generated = caption_model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=inputs["pixel_values"],
            max_new_tokens=48,
            num_beams=1,
            do_sample=False,
        )
        label = caption_processor.batch_decode(generated, skip_special_tokens=True)[0].strip()
        out.append(
            (label, confidence, (x1 / width, y1 / height, (x2 - x1) / width, (y2 - y1) / height))
        )
    return out
