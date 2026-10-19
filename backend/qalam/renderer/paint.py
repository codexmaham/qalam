"""Rasterise shaped glyphs onto a page."""

from __future__ import annotations

import freetype
from PIL import Image, ImageDraw

from qalam.renderer.fonts import FontLibrary
from qalam.renderer.jitter import ShapedGlyph

_LOAD_FLAGS = freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING


def _glyph_image(face: freetype.Face, glyph_id: int) -> tuple[Image.Image | None, int, int]:
    face.load_glyph(glyph_id, _LOAD_FLAGS)
    slot = face.glyph
    bitmap = slot.bitmap
    if bitmap.width == 0 or bitmap.rows == 0 or bitmap.pixel_mode != freetype.FT_PIXEL_MODE_GRAY:
        return None, slot.bitmap_left, slot.bitmap_top
    pitch = bitmap.pitch
    raw = bytes(bitmap.buffer)
    width = bitmap.width
    rows = []
    if pitch > 0:
        for row in range(bitmap.rows):
            start = row * pitch
            rows.append(raw[start : start + width])
    else:
        pitch = -pitch
        for row in range(bitmap.rows - 1, -1, -1):
            start = row * pitch
            rows.append(raw[start : start + width])
    return Image.frombytes("L", (width, bitmap.rows), b"".join(rows)), slot.bitmap_left, slot.bitmap_top


def _tint(gray: Image.Image, rgb: tuple[int, int, int], alpha_mul: float) -> Image.Image:
    lut = [min(255, int(value * alpha_mul)) for value in range(256)]
    alpha = gray.point(lut)
    colored = Image.new("RGBA", gray.size, (*rgb, 0))
    colored.putalpha(alpha)
    return colored


def _blit(page: Image.Image, sprite: Image.Image, x: int, y: int) -> None:
    if sprite.width == 0 or sprite.height == 0:
        return
    src_x = 0 if x >= 0 else -x
    src_y = 0 if y >= 0 else -y
    dest_x = max(0, x)
    dest_y = max(0, y)
    width = min(sprite.width - src_x, page.width - dest_x)
    height = min(sprite.height - src_y, page.height - dest_y)
    if width <= 0 or height <= 0:
        return
    crop = sprite.crop((src_x, src_y, src_x + width, src_y + height))
    page.alpha_composite(crop, (dest_x, dest_y))


def draw_glyphs(
    page: Image.Image,
    glyphs: list[ShapedGlyph],
    origin_x: float,
    baseline: float,
    px: float,
    library: FontLibrary,
    rgb: tuple[int, int, int],
    ink_alpha: float,
) -> None:
    """Draw glyphs left to right. HarfBuzz already returns visual order."""

    pen = origin_x
    for glyph in glyphs:
        face = library.prepare_freetype(glyph.font_id, px)
        gray, left, top = _glyph_image(face, glyph.glyph_id)
        scale = glyph.scale if glyph.scale > 0 else 1
        if gray is not None:
            sprite = _tint(gray, rgb, ink_alpha * glyph.alpha)
            if abs(scale - 1) > 0.015:
                sprite = sprite.resize(
                    (max(1, round(sprite.width * scale)), max(1, round(sprite.height * scale))),
                    Image.Resampling.BICUBIC,
                )
            draw_x = pen + glyph.x_offset + left * scale
            draw_y = baseline - glyph.y_jitter - glyph.y_offset - top * scale
            if abs(glyph.rotation) > 0.25:
                center_x = draw_x + sprite.width / 2
                center_y = draw_y + sprite.height / 2
                sprite = sprite.rotate(
                    glyph.rotation,
                    expand=True,
                    resample=Image.Resampling.BICUBIC,
                )
                draw_x = center_x - sprite.width / 2
                draw_y = center_y - sprite.height / 2
            _blit(page, sprite, int(round(draw_x)), int(round(draw_y)))
        pen += glyph.x_advance


def measure_width(glyphs: list[ShapedGlyph]) -> float:
    return sum(glyph.x_advance for glyph in glyphs)


def draw_text(
    page: Image.Image,
    glyphs: list[ShapedGlyph],
    x: float,
    baseline: float,
    px: float,
    library: FontLibrary,
    rgb: tuple[int, int, int],
    ink_alpha: float = 1,
) -> float:
    draw_glyphs(page, glyphs, x, baseline, px, library, rgb, ink_alpha)
    return measure_width(glyphs)


def hline(draw: ImageDraw.ImageDraw, x0: int, x1: int, y: int, color: tuple, width: int) -> None:
    draw.line((x0, y, x1, y), fill=color, width=width)


def dotted_hline(
    draw: ImageDraw.ImageDraw,
    x0: int,
    x1: int,
    y: int,
    color: tuple,
    width: int,
    step: int,
) -> None:
    dash = max(2, step // 2)
    x = x0
    while x < x1:
        draw.line((x, y, min(x + dash, x1), y), fill=color, width=width)
        x += step
