from __future__ import annotations

import pytest

from lazyworker.interaction.textcolor import read_text_color

Image = pytest.importorskip("PIL.Image")
ImageDraw = pytest.importorskip("PIL.ImageDraw")
ImageFont = pytest.importorskip("PIL.ImageFont")

W, H = 200, 40


def _font():
    for path in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        try:
            return ImageFont.truetype(path, 30)
        except OSError:
            continue
    return ImageFont.load_default()


FONT = _font()


def _solid(bg, text=None, fill=None, multicolor=None):
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    if multicolor:
        x = 8
        for i, ch in enumerate(text):
            d.text((x, 4), ch, fill=multicolor[i % len(multicolor)], font=FONT)
            x += int(d.textlength(ch, font=FONT)) + 1
    elif text:
        d.text((8, 4), text, fill=fill, font=FONT)
    return img


def _vgrad(top, bot, text=None, fill=None):
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for r in range(H):
        t = r / (H - 1)
        d.line([(0, r), (W, r)], fill=tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
    if text:
        ImageDraw.Draw(img).text((8, 4), text, fill=fill, font=FONT)
    return img


def _close(a, b, tol=34.0):
    return sum((x - y) ** 2 for x, y in zip(a, b, strict=False)) ** 0.5 <= tol


def test_white_text_on_red_solid():
    r = read_text_color(_solid((200, 30, 40), "Hello", fill=(255, 255, 255)))
    assert r.solid_background and r.note == "ok"
    assert _close(r.text, (255, 255, 255))
    assert _close(r.background, (200, 30, 40))


def test_red_text_on_white_solid():
    r = read_text_color(_solid((250, 250, 250), "Começar", fill=(220, 50, 50)))
    assert _close(r.text, (220, 50, 50))
    assert _close(r.background, (250, 250, 250))


def test_light_text_on_dark():
    r = read_text_color(_solid((20, 20, 26), "Settings", fill=(235, 235, 240)))
    assert _close(r.text, (235, 235, 240))


def test_text_on_steep_gradient():
    r = read_text_color(_vgrad((40, 60, 220), (240, 210, 40), "Gradient", fill=(10, 10, 10)))
    assert _close(r.text, (10, 10, 10))
    assert not r.solid_background and r.note == "gradient_background"


def test_very_low_contrast_abstains():
    r = read_text_color(_solid((210, 210, 210), "faint", fill=(196, 196, 196)))
    assert r.text is None and r.note in ("no_text", "low_contrast")


def test_empty_box_has_no_text():
    r = read_text_color(_solid((245, 246, 248)))
    assert r.text is None and r.note == "no_text"
    assert _close(r.background, (245, 246, 248))


def test_multicolour_text_is_flagged():
    r = read_text_color(
        _solid((250, 250, 250), "RGB", multicolor=[(220, 30, 30), (30, 160, 30), (30, 30, 220)])
    )
    assert r.note == "multicolour" or r.text is None


# --- Interactor integration: resolve element -> crop -> read ----------------


class _FakeSession:
    def __init__(self, tree, png: bytes) -> None:
        self._tree = tree
        self._png = png

    def source(self):
        return self._tree

    def screenshot(self) -> bytes:
        return self._png


def test_interactor_color_resolves_and_reads():
    import io

    from lazyworker.interaction.interactor import Interactor
    from lazyworker.interaction.locator import Locator
    from lazyworker.wda.models import AccessibilityNode, Rect

    child = AccessibilityNode(
        type="StaticText", identifier="label-1", visible=True,
        rect=Rect(x=10, y=10, width=60, height=20), children=[],
    )
    root = AccessibilityNode(
        type="Window", visible=True, rect=Rect(x=0, y=0, width=100, height=100), children=[child]
    )
    # scale = screenshot width / window width = 100 / 100 = 1. White box with a red
    # "ink" block inside the element rect (the interactor crops (10,10)-(70,30)).
    img = Image.new("RGB", (100, 100), (250, 250, 250))
    ImageDraw.Draw(img).rectangle([22, 14, 58, 26], fill=(220, 50, 50))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    interactor = Interactor(_FakeSession(root, buf.getvalue()))  # type: ignore[arg-type]
    result = interactor.color(Locator(identifier="label-1"))
    assert result.ok and result.element is not None
    assert _close(result.background, (250, 250, 250))
    assert result.text is not None and _close(result.text, (220, 50, 50))


def test_interactor_color_not_found():
    from lazyworker.interaction.interactor import Interactor
    from lazyworker.interaction.locator import Locator
    from lazyworker.wda.models import AccessibilityNode, Rect

    root = AccessibilityNode(type="Window", visible=True, rect=Rect(x=0, y=0, width=10, height=10))
    interactor = Interactor(_FakeSession(root, b""))  # type: ignore[arg-type]
    result = interactor.color(Locator(identifier="missing"))
    assert not result.ok and result.error_code.value == "not_found"
