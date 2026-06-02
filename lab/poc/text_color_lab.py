"""Text colour extraction lab.

Builds many synthetic "text box" cases (solid/gradient/photo backgrounds, light
and dark text, low contrast, multicolour text, emoji-like glyphs, empty boxes)
with KNOWN ground truth, then scores several segmentation strategies on each.
Goal: find a small set of strategies (one default + adaptations) that covers the
most cases. Run: lab/poc/.venv/bin/python lab/poc/text_color_lab.py
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

TOL = 34.0  # max RGB distance to call a recovered text colour "correct"

# --- fonts -------------------------------------------------------------------

def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


FONT = _font(30)
SMALL = _font(13)


# --- backgrounds -------------------------------------------------------------

def solid(w, h, color):
    return np.full((h, w, 3), color, np.uint8)


def vgrad(w, h, top, bot):
    out = np.zeros((h, w, 3), np.uint8)
    for r in range(h):
        t = r / max(h - 1, 1)
        out[r, :] = [int(top[i] + (bot[i] - top[i]) * t) for i in range(3)]
    return out


def hgrad(w, h, left, right):
    return np.transpose(vgrad(h, w, left, right), (1, 0, 2))


def photo(w, h, seed):
    rng = np.random.RandomState(seed)
    base = rng.randint(0, 256, (h, w, 3)).astype(np.uint8)
    return np.asarray(Image.fromarray(base).filter(ImageFilter.GaussianBlur(3)))


def draw(bg: np.ndarray, text: str, color=None, font=FONT, multicolor=None, emoji=False):
    img = Image.fromarray(bg.copy())
    d = ImageDraw.Draw(img)
    if emoji:
        # multi-colour glyph proxy: overlapping coloured discs
        for i, c in enumerate([(255, 60, 60), (60, 200, 60), (60, 120, 255)]):
            d.ellipse([8 + i * 24, 6, 30 + i * 24, 28], fill=c)
        return np.asarray(img)
    if multicolor:
        x = 8
        for i, ch in enumerate(text):
            c = multicolor[i % len(multicolor)]
            d.text((x, 4), ch, fill=c, font=font)
            x += int(d.textlength(ch, font=font)) + 1
        return np.asarray(img)
    d.text((8, 4), text, fill=color, font=font)
    return np.asarray(img)


# --- cases (name, image, truth) ----------------------------------------------
# truth: {"kind": "solid"|"multicolor"|"none", "text": rgb|None}

def build_cases():
    W, H = 200, 40
    C = []
    C.append(("solid_white_on_red", draw(solid(W, H, (200, 30, 40)), "Hello 123", (255, 255, 255)),
              {"kind": "solid", "text": (255, 255, 255)}))
    C.append(("solid_red_on_white", draw(solid(W, H, (250, 250, 250)), "Começar", (220, 50, 50)),
              {"kind": "solid", "text": (220, 50, 50)}))
    C.append(("dark_mode", draw(solid(W, H, (20, 20, 26)), "Settings", (235, 235, 240)),
              {"kind": "solid", "text": (235, 235, 240)}))
    C.append(("low_contrast", draw(solid(W, H, (210, 210, 210)), "subtle", (170, 170, 170)),
              {"kind": "solid", "text": (170, 170, 170)}))
    C.append(("very_low_contrast", draw(solid(W, H, (210, 210, 210)), "faint", (195, 195, 195)),
              {"kind": "solid", "text": (195, 195, 195)}))
    C.append(("grad_gentle_white", draw(vgrad(W, H, (200, 20, 30), (210, 60, 60)), "Sua musica", (255, 255, 255)),
              {"kind": "solid", "text": (255, 255, 255)}))
    C.append(("grad_steep_black", draw(vgrad(W, H, (40, 60, 220), (240, 210, 40)), "Gradient", (10, 10, 10)),
              {"kind": "solid", "text": (10, 10, 10)}))
    C.append(("grad_horizontal_white", draw(hgrad(W, H, (10, 80, 30), (10, 160, 60)), "Horizon", (255, 255, 255)),
              {"kind": "solid", "text": (255, 255, 255)}))
    C.append(("photo_white", draw(photo(W, H, 1), "OnPhoto", (255, 255, 255)),
              {"kind": "solid", "text": (255, 255, 255)}))
    C.append(("photo_black", draw(photo(W, H, 2), "OnPhoto", (5, 5, 5)),
              {"kind": "solid", "text": (5, 5, 5)}))
    C.append(("small_text", draw(solid(W, 22, (245, 245, 245)), "tiny label here", (40, 40, 40), font=SMALL),
              {"kind": "solid", "text": (40, 40, 40)}))
    C.append(("multicolor_text", draw(solid(W, H, (250, 250, 250)), "RAINBOW",
                                       multicolor=[(220, 30, 30), (30, 160, 30), (30, 30, 220)]),
              {"kind": "multicolor", "text": None}))
    C.append(("emoji_glyph", draw(solid(W, H, (250, 250, 250)), "", emoji=True),
              {"kind": "multicolor", "text": None}))
    C.append(("empty_solid", solid(W, H, (245, 246, 248)), {"kind": "none", "text": None}))
    C.append(("empty_gradient", vgrad(W, H, (180, 20, 30), (220, 70, 70)), {"kind": "none", "text": None}))
    return C


# --- helpers -----------------------------------------------------------------

def luma(a):
    return 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]


def dist(a, b):
    return float(np.sqrt(((np.array(a, float) - np.array(b, float)) ** 2).sum()))


def _result(fg_pixels, bg_pixels):
    """Build a strategy result from foreground/background pixel sets."""
    n = len(fg_pixels) + len(bg_pixels)
    frac = len(fg_pixels) / n if n else 0.0
    if len(fg_pixels) < max(8, 0.005 * n) or frac > 0.6:
        return {"text": None, "bg": None, "frac": frac, "text_std": None, "reason": "no_text"}
    text = tuple(int(v) for v in np.median(fg_pixels, axis=0))
    bg = tuple(int(v) for v in np.median(bg_pixels, axis=0)) if len(bg_pixels) else None
    text_std = float(np.mean(np.std(fg_pixels, axis=0)))
    return {"text": text, "bg": bg, "frac": frac, "text_std": text_std, "reason": "ok"}


# --- strategies --------------------------------------------------------------

def s_global_mode(crop):
    flat = crop.reshape(-1, 3).astype(np.int32)
    bg = np.array(__import__("collections").Counter(map(tuple, flat // 16)).most_common(1)[0][0]) * 16 + 8
    d = np.sqrt(((flat - bg) ** 2).sum(1))
    if d.max() < 40:
        return _result(flat[:0], flat)
    m = d > d.max() * 0.5
    return _result(flat[m], flat[~m])


def s_border_bg(crop):
    h, w, _ = crop.shape
    border = np.concatenate([crop[0], crop[-1], crop[:, 0], crop[:, -1]]).astype(np.int32)
    bg = np.median(border, axis=0)
    flat = crop.reshape(-1, 3).astype(np.int32)
    d = np.sqrt(((flat - bg) ** 2).sum(1))
    if d.max() < 40:
        return _result(flat[:0], flat)
    m = d > d.max() * 0.5
    return _result(flat[m], flat[~m])


def s_otsu(crop):
    L = luma(crop)
    hist, _ = np.histogram(L, bins=256, range=(0, 255))
    total = L.size
    sumT = np.dot(np.arange(256), hist)
    wB = sB = 0.0
    best_t, best_var = 0, -1.0
    for t in range(256):
        wB += hist[t]
        if wB == 0:
            continue
        wF = total - wB
        if wF == 0:
            break
        sB += t * hist[t]
        mB = sB / wB
        mF = (sumT - sB) / wF
        var = wB * wF * (mB - mF) ** 2
        if var > best_var:
            best_var, best_t = var, t
    flat = crop.reshape(-1, 3).astype(np.int32)
    Lf = L.reshape(-1)
    dark = Lf < best_t
    fg = dark if dark.mean() < 0.5 else ~dark  # text = minority class
    return _result(flat[fg], flat[~fg])


def s_perrow(crop):
    a = crop.astype(np.int32)
    rowbg = np.median(a, axis=1, keepdims=True)
    d = np.sqrt(((a - rowbg) ** 2).sum(2))
    if d.max() < 40:
        return _result(a.reshape(-1, 3)[:0], a.reshape(-1, 3))
    m = (d > d.max() * 0.5).reshape(-1)
    flat = a.reshape(-1, 3)
    return _result(flat[m], flat[~m])


def _box_mean(a, win):
    r = max(win // 2, 1)
    k = 2 * r + 1
    pad = np.pad(a, r, mode="edge")
    cs = np.pad(np.cumsum(np.cumsum(pad, 0), 1), ((1, 0), (1, 0)))
    h, w = a.shape
    s = cs[k:k + h, k:k + w] - cs[0:h, k:k + w] - cs[k:k + h, 0:w] + cs[0:h, 0:w]
    return s / (k * k)


def s_sauvola(crop, win=15, k=0.2, R=128.0):
    L = luma(crop).astype(np.float64)
    mean = _box_mean(L, win)
    meansq = _box_mean(L * L, win)
    std = np.sqrt(np.clip(meansq - mean * mean, 0, None))
    thr = mean * (1 + k * (std / R - 1))
    flat = crop.reshape(-1, 3).astype(np.int32)
    dark = (L < thr).reshape(-1)
    fg = dark if dark.mean() < 0.5 else ~dark
    if fg.mean() < 0.003 or fg.mean() > 0.6:
        return _result(flat[:0], flat)
    return _result(flat[fg], flat[~fg])


STRATEGIES = {
    "global_mode": s_global_mode,
    "border_bg": s_border_bg,
    "otsu": s_otsu,
    "perrow": s_perrow,
    "sauvola": s_sauvola,
}


# --- scoring -----------------------------------------------------------------

def score(case_truth, res):
    kind = case_truth["kind"]
    if kind == "none":
        return res["reason"] == "no_text"
    if kind == "multicolor":
        # success = NOT confidently reporting a single colour (abstain or flag high spread)
        return res["reason"] == "no_text" or (res["text_std"] is not None and res["text_std"] > 45)
    # solid: recovered text colour within tolerance
    return res["text"] is not None and dist(res["text"], case_truth["text"]) <= TOL


def main():
    cases = build_cases()
    names = list(STRATEGIES)
    print(f"{'case':24}", "  ".join(f"{n:>11}" for n in names))
    totals = dict.fromkeys(names, 0)
    for cname, img, truth in cases:
        cells = []
        for sname in names:
            res = STRATEGIES[sname](img)
            ok = score(truth, res)
            totals[sname] += ok
            if truth["kind"] == "solid" and res["text"] is not None:
                cells.append(f"{'OK' if ok else 'X'}({int(dist(res['text'], truth['text'])):>3})")
            else:
                cells.append(("OK" if ok else "X") + f"[{res['reason'][:4]}]")
        print(f"{cname:24}", "  ".join(f"{c:>11}" for c in cells))
    print(f"\n{'TOTAL /'+str(len(cases)):24}", "  ".join(f"{totals[n]:>11}" for n in names))


if __name__ == "__main__":
    main()
