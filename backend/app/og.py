"""Social preview images (Open Graph, 1200x630) drawn with Pillow.

One per page: the brand gradient, the logo, a label (source or section),
the title and a footer line. Cached on disk by content, so a changed title
gets a new file (and a new ?v= in og:image, which busts social caches).
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

from .config import settings

W, H = 1200, 630
SCALE = 2  # drawn at 2x and scaled down: smooth edges without per-shape antialiasing
FONTS = Path(__file__).parent / "assets" / "fonts"
STOPS = [(0.0, (0x1E, 0x3A, 0x8A)), (0.55, (0x25, 0x63, 0xEB)), (1.0, (0x38, 0xBD, 0xF8))]


@lru_cache(maxsize=16)
def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"Inter-{weight}.ttf"), size * SCALE)


def _gradient(w: int, h: int) -> Image.Image:
    """The brand gradient, top-left to bottom-right like the SVG icon
    (t = (x/w + y/h) / 2, mapped through the three colour stops)."""
    ramp = Image.linear_gradient("L")  # 256x256, black at the top
    ty = ramp.resize((w, h))
    tx = ramp.rotate(90).resize((w, h))  # black on the left
    t = ImageChops.add(tx, ty, scale=2.0)
    palette: list[int] = []
    for i in range(256):
        v = i / 255
        for (t0, c0), (t1, c1) in zip(STOPS, STOPS[1:]):
            if t0 <= v <= t1:
                f = (v - t0) / (t1 - t0)
                palette += [round(a + (b - a) * f) for a, b in zip(c0, c1)]
                break
    t.putpalette(palette)  # an "L" image with a palette becomes "P"
    return t.convert("RGB")


def _logo(size: int) -> Image.Image:
    """The app icon (white U and light dot on the gradient tile)."""
    s = size
    tile = _gradient(s, s)
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, s - 1, s - 1), radius=round(s * 116 / 512), fill=255)
    out = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    out.paste(tile, (0, 0), mask)
    d = ImageDraw.Draw(out)
    k = s / 512
    sw = round(52 * k)
    # U: two legs and the bottom half circle (centre 256,276 r=90), round caps
    d.line([(166 * k, 150 * k), (166 * k, 276 * k)], fill="white", width=sw)
    d.line([(346 * k, 150 * k), (346 * k, 276 * k)], fill="white", width=sw)
    r = 90 * k
    d.arc([(256 * k - r - sw / 2, 276 * k - r - sw / 2), (256 * k + r + sw / 2, 276 * k + r + sw / 2)],
          0, 180, fill="white", width=sw)
    for x in (166, 346):
        d.ellipse([(x * k - sw / 2, 150 * k - sw / 2), (x * k + sw / 2, 150 * k + sw / 2)], fill="white")
    d.ellipse([(338 * k, 98 * k), (418 * k, 178 * k)], fill="white")
    d.ellipse([(345 * k, 105 * k), (411 * k, 171 * k)], fill=(0xBA, 0xE6, 0xFD))
    return out


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int, lines: int) -> list[str]:
    words, out, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= width:
            cur = trial
            continue
        if cur:
            out.append(cur)
        cur = w
        if len(out) == lines:
            break
    if cur and len(out) < lines:
        out.append(cur)
    if len(out) == lines and " ".join(out) != " ".join(words):
        last = out[-1]
        while last and draw.textlength(last + "…", font=font) > width:
            last = last[:-1].rstrip()
        out[-1] = last + "…"
    return out


def render(title: str, label: str = "", footer: str = "") -> bytes:
    import io

    w, h = W * SCALE, H * SCALE
    img = _gradient(w, h)
    d = ImageDraw.Draw(img, "RGBA")  # RGB image + RGBA colours = translucent shapes blend in
    # Soft circles, as in the app's banners
    d.ellipse([(w - 520 * SCALE, -260 * SCALE), (w + 140 * SCALE, 400 * SCALE)], fill=(255, 255, 255, 22))
    d.ellipse([(w - 330 * SCALE, h - 230 * SCALE), (w + 30 * SCALE, h + 130 * SCALE)], fill=(255, 255, 255, 18))

    pad = 80 * SCALE
    logo = _logo(84 * SCALE)
    ly = 70 * SCALE
    d.rounded_rectangle([(pad - 3 * SCALE, ly - 3 * SCALE), (pad + 87 * SCALE, ly + 87 * SCALE)],
                        radius=22 * SCALE, fill=(255, 255, 255, 60))  # lifts the tile off the same gradient
    img.paste(logo, (pad, ly), logo)
    brand = _font("Bold", 46)
    d.text((pad + 108 * SCALE, 70 * SCALE + 42 * SCALE), "Open Unifi", font=brand, fill="white", anchor="lm")

    y = 228 * SCALE
    if label:
        f = _font("Medium", 26)
        text = label.upper()
        tw = d.textlength(text, font=f)
        d.rounded_rectangle([(pad, y), (pad + tw + 36 * SCALE, y + 50 * SCALE)], radius=25 * SCALE,
                            fill=(255, 255, 255, 38))
        d.text((pad + 18 * SCALE, y + 25 * SCALE), text, font=f, fill="white", anchor="lm")
        y += 78 * SCALE

    size = 64 if len(title) < 60 else 54 if len(title) < 110 else 46
    f = _font("Bold", size)
    room = (H - 120) * SCALE - y
    max_lines = max(1, min(4, room // round(size * 1.18 * SCALE)))
    for line in _wrap(d, title, f, w - 2 * pad, max_lines):
        d.text((pad, y), line, font=f, fill="white")
        y += round(size * 1.18 * SCALE)

    if footer:
        d.text((pad, h - 70 * SCALE), footer, font=_font("Medium", 28), fill=(255, 255, 255, 215), anchor="lm")

    out = io.BytesIO()
    img.resize((W, H), Image.LANCZOS).save(out, "PNG", optimize=True)
    return out.getvalue()


def version(title: str, label: str, footer: str) -> str:
    return hashlib.sha1(f"2|{title}|{label}|{footer}".encode()).hexdigest()[:10]


def cached(key: str, title: str, label: str = "", footer: str = "") -> Path:
    """Path of the PNG for this content, drawing it the first time."""
    folder = Path(settings.data_dir) / "og"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{key}-{version(title, label, footer)}.png"
    if not path.exists():
        for old in folder.glob(f"{key}-*.png"):  # previous versions of this page
            old.unlink(missing_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(render(title, label, footer))
        tmp.replace(path)
    return path
