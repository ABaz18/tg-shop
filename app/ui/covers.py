from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
BG = (18, 20, 26)
INK = (244, 241, 234)
MUTED = (139, 138, 134)
LINE = (42, 44, 52)
GOLD = (200, 169, 106)
ACCENTS = (
    GOLD,
    (138, 154, 123),
    (122, 139, 156),
    (193, 122, 90),
)
LAYOUT = "big1"

_FONT_BOLD = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    Path("C:/Windows/Fonts/segoeuib.ttf"),
    Path("C:/Windows/Fonts/arialbd.ttf"),
)
_FONT_REG = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    Path("C:/Windows/Fonts/segoeui.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
)


def _font(paths: tuple[Path, ...], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in paths:
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: int, max_lines: int = 3) -> list[str]:
    words = (text or "").strip().split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = word
        if len(lines) >= max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines:
        last = lines[-1]
        while draw.textlength(last + "…", font=font) > max_w and last:
            last = last[:-1]
        if last != lines[-1]:
            lines[-1] = last.rstrip() + "…"
    return lines


def _mark(draw: ImageDraw.ImageDraw, x: int, y: int, accent: tuple[int, int, int]) -> None:
    draw.rectangle((x, y, x + 36, y + 36), outline=accent, width=3)
    draw.rectangle((x + 14, y + 14, x + 50, y + 50), fill=accent)


def _canvas(accent: tuple[int, int, int]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(im)
    draw.rectangle((0, 0, 12, H), fill=accent)
    for x in range(80, W, 80):
        draw.line((x, 0, x, H), fill=LINE, width=1)
    for y in range(80, H, 80):
        draw.line((0, y, W, y), fill=LINE, width=1)
    draw.rectangle((0, 0, 12, H), fill=accent)
    draw.rectangle((36, 36, W - 36, H - 36), outline=LINE, width=1)
    return im, draw


def render_page(
    *,
    eyebrow: str,
    title: str,
    subtitle: str = "",
    footer: str = "",
    accent: int = 0,
) -> bytes:
    color = ACCENTS[accent % len(ACCENTS)]
    im, draw = _canvas(color)
    bold = _font(_FONT_BOLD, 76)
    reg = _font(_FONT_REG, 34)
    small = _font(_FONT_REG, 24)
    left = 64
    max_w = W - 128
    _mark(draw, left, 64, color)
    draw.text((left + 70, 74), (eyebrow or "").upper(), font=small, fill=color)
    y = 150
    for line in _wrap(draw, title or " ", bold, max_w, 3):
        draw.text((left, y), line, font=bold, fill=INK)
        y += 86
    draw.line((left, y + 8, left + 220, y + 8), fill=color, width=4)
    if subtitle:
        y += 28
        for line in _wrap(draw, subtitle, reg, max_w, 3):
            draw.text((left, y), line, font=reg, fill=MUTED)
            y += 42
    if footer:
        draw.text((left, H - 100), footer[:90], font=small, fill=MUTED)
    return _jpeg(im)


def render_shop_banner(title: str, subtitle: str, eyebrow: str = "МАГАЗИН") -> bytes:
    return render_page(
        eyebrow=eyebrow,
        title=(title or "SHOP").upper(),
        subtitle=subtitle,
        footer="оплата  ·  выдача  ·  поддержка в чате",
        accent=0,
    )


def render_category_cover(title: str, count: int, seed: int = 0, eyebrow: str = "КАТАЛОГ") -> bytes:
    return render_page(
        eyebrow=eyebrow,
        title=title,
        footer="нажмите товар ниже",
        accent=seed,
    )


def render_product_cover(title: str, price: str, badge: str) -> bytes:
    accent = GOLD
    im, draw = _canvas(accent)
    bold = _font(_FONT_BOLD, 72)
    price_f = _font(_FONT_BOLD, 64)
    small = _font(_FONT_REG, 24)
    left = 64
    max_w = W - 128
    _mark(draw, left, 64, accent)
    draw.text((left + 70, 74), "ТОВАР", font=small, fill=accent)
    bw = int(draw.textlength(badge, font=small)) + 48
    draw.rounded_rectangle((left, 140, left + bw, 196), radius=4, outline=accent, width=2)
    draw.text((left + 22, 154), badge, font=small, fill=accent)
    y = 230
    for line in _wrap(draw, title, bold, max_w, 3):
        draw.text((left, y), line, font=bold, fill=INK)
        y += 82
    draw.line((left, H - 168, W - 64, H - 168), fill=LINE, width=1)
    draw.text((left, H - 130), price, font=price_f, fill=INK)
    draw.text((W - 64, H - 112), "после оплаты", font=small, fill=MUTED, anchor="rt")
    return _jpeg(im)


def _jpeg(im: Image.Image) -> bytes:
    buf = BytesIO()
    im.save(buf, format="JPEG", quality=90, optimize=True, progressive=True)
    return buf.getvalue()


def cover_key(*parts: object) -> str:
    raw = "|".join(str(p) for p in (LAYOUT, *parts))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def jpeg_file(data: bytes, name: str = "cover.jpg"):
    from aiogram.types import BufferedInputFile

    return BufferedInputFile(data, filename=name)
