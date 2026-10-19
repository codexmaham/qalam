"""Draw new text from a style's letters, on ruled paper or on a photo.

Characters the sample does not contain are shaped with the closest bundled
font. The sample's slant turns into that font's jitter amount. A one-shot
model can replace this module later; callers only see `render`.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from qalam.models import RenderRequest, RenderResult
from qalam.registry import ink_by_id
from qalam.renderer.engine import FontHandwritingRenderer
from qalam.renderer.jitter import apply_jitter, rng_for
from qalam.renderer.paint import draw_glyphs, measure_width
from qalam.renderer.segment import dominant_script, segment
from qalam.renderer.templates import PageGeometry, a4_px, make_page, mm
from qalam.styles.model import GlyphVariant, HandwritingStyle
from qalam.styles.pagephoto import PreparedPage

MAX_CHARS = 12000


def _raster(variant: GlyphVariant, x_height: float, scale_jitter: float) -> tuple[np.ndarray, int, int] | None:
    scale = x_height * scale_jitter
    if scale < 1 or not variant.outers:
        return None

    def rings(source: list[list[list[float]]]) -> list[list[tuple[float, float]]]:
        converted = []
        for ring in source:
            if len(ring) < 3:
                continue
            converted.append([(p[0] * scale, -p[1] * scale) for p in ring])
        return converted

    outers = rings(variant.outers)
    holes = rings(variant.holes)
    if not outers:
        return None
    xs = [p[0] for ring in outers + holes for p in ring]
    ys = [p[1] for ring in outers + holes for p in ring]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    pad = 1
    width = max(1, int(np.ceil(max_x - min_x)) + pad * 2)
    height = max(1, int(np.ceil(max_y - min_y)) + pad * 2)
    mask = np.zeros((height, width), np.uint8)

    def shift(source: list[list[tuple[float, float]]]) -> list[np.ndarray]:
        arrays = []
        for ring in source:
            arrays.append(
                np.array(
                    [[int(round(p[0] - min_x + pad)), int(round(p[1] - min_y + pad))] for p in ring],
                    dtype=np.int32,
                )
            )
        return arrays

    import cv2

    cv2.fillPoly(mask, shift(outers), 255)
    if holes:
        cv2.fillPoly(mask, shift(holes), 0)
    if int(mask.sum()) < 30:
        return None
    baseline = int(round(-min_y + pad))
    origin = int(round(min_x - pad))
    return mask, baseline, origin


def _blit(page: Image.Image, mask: np.ndarray, x: int, y: int, rgb: tuple[int, int, int], alpha: float) -> None:
    height, width = mask.shape
    if width == 0 or height == 0:
        return
    sprite = np.zeros((height, width, 4), np.uint8)
    sprite[:, :, 0] = rgb[0]
    sprite[:, :, 1] = rgb[1]
    sprite[:, :, 2] = rgb[2]
    sprite[:, :, 3] = np.clip(mask.astype(np.float32) * alpha, 0, 255).astype(np.uint8)
    image = Image.fromarray(sprite, "RGBA")
    src_x = 0 if x >= 0 else -x
    src_y = 0 if y >= 0 else -y
    dest_x = max(0, x)
    dest_y = max(0, y)
    crop_w = min(image.width - src_x, page.width - dest_x)
    crop_h = min(image.height - src_y, page.height - dest_y)
    if crop_w <= 0 or crop_h <= 0:
        return
    page.alpha_composite(image.crop((src_x, src_y, src_x + crop_w, src_y + crop_h)), (dest_x, dest_y))


def _multiply(page: Image.Image, overlay: Image.Image) -> None:
    base = np.array(page).astype(np.float32)
    over = np.array(overlay).astype(np.float32)
    alpha = over[:, :, 3:4] / 255.0
    ink = over[:, :, :3]
    paper = base[:, :, :3]
    mixed = paper * (1 - alpha) + (paper * ink / 255.0) * alpha
    base[:, :, :3] = mixed
    page.paste(Image.fromarray(base.astype(np.uint8), "RGBA"))


def _covered(style: HandwritingStyle, text: str) -> bool:
    if style.engine != "glyphs":
        return False
    letters = [ch for ch in text if not ch.isspace()]
    if not letters:
        return False
    if dominant_script(text) not in {"Latn", "Zyyy"}:
        return False
    return all(style.has_char(ch) for ch in letters)


def _median_width(style: HandwritingStyle, ch: str) -> float:
    variants = style.glyphs.get(ch) or []
    if not variants:
        return 0.6
    return float(np.median([v.width for v in variants]))


def render_styled(
    fonts: FontHandwritingRenderer,
    request: RenderRequest,
    style: HandwritingStyle,
    photo: PreparedPage | None,
) -> RenderResult:
    language = fonts.registry.language(request.language_id)
    if photo is None and request.template_id in {"tianzige", "square-grid"}:
        return fonts.render(request)

    text = request.text.replace("\r\n", "\n").replace("\r", "\n")
    truncated = False
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]
        truncated = True

    if request.ink_id == "sample":
        rgb = style.stats.ink_rgb
        alpha = 0.94
    else:
        ink = ink_by_id(request.ink_id)
        rgb = ink["rgb"]
        alpha = ink["alpha"]

    pages: list[Image.Image] = []
    line_mm = fonts.registry.font(language.font).line_mm
    page, slots, line_h = _open_page(request, language.direction, photo, line_mm)
    _header(fonts, page, request, language, rgb, alpha, photo)
    slot = 0
    paragraphs = text.split("\n")
    overflow = False

    def newline() -> bool:
        nonlocal page, slots, line_h, slot, overflow
        slot += 1
        if slot < len(slots):
            return True
        if len(pages) + 1 >= request.max_pages:
            overflow = True
            return False
        _number(fonts, page, len(pages) + 1, request.dpi)
        pages.append(page.image)
        page, slots, line_h = _open_page(request, language.direction, photo, line_mm)
        _header(fonts, page, request, language, rgb, alpha, photo)
        slot = 0
        return True

    x_height = _x_height(request.template_id, line_h, style, photo is not None)
    for para_index, paragraph in enumerate(paragraphs):
        if paragraph == "" and para_index < len(paragraphs) - 1:
            if not newline():
                break
            continue
        rest = paragraph
        first = True
        while rest:
            if slot >= len(slots) and not newline():
                rest = ""
                break
            indent = x_height * 1.1 if first and _width_of(fonts, style, rest, language, x_height, request, rgb) > page.width else 0
            line, rest = _take(fonts, style, rest, language, page.width - indent, x_height, request, rgb)
            if not line and rest:
                # A single piece wider than the page: draw it anyway and move on.
                line, rest = rest[:1], rest[1:]
            _draw_line(
                fonts,
                page,
                line,
                slots[slot],
                indent,
                language,
                style,
                x_height,
                rgb,
                alpha,
                request,
                photo is not None,
                para_index,
            )
            slot += 1
            first = False
            if slot >= len(slots) and rest:
                if not newline():
                    break
    if all(existing is not page.image for existing in pages):
        _number(fonts, page, len(pages) + 1, request.dpi)
        pages.append(page.image)
    rgb_pages = [p.convert("RGB") for p in pages] or [page.image.convert("RGB")]
    return RenderResult(
        pages=rgb_pages,
        truncated=truncated or overflow,
        width=rgb_pages[0].width,
        height=rgb_pages[0].height,
    )


def _open_page(request, direction, photo: PreparedPage | None, line_mm: float):
    if photo is None:
        page = make_page(request.template_id, request.dpi, direction, line_mm)
        return page, page.baselines(), page.line_height

    width, height = a4_px(request.dpi)
    resized = Image.fromarray(cv2_rgb(photo.image), "RGB").resize((width, height), Image.Resampling.LANCZOS)
    image = resized.convert("RGBA")
    baselines = [int(y * height) for y in photo.lines if 0.07 < y < 0.96]
    if len(baselines) < 2:
        baselines = [int(height * y) for y in (0.18, 0.26, 0.34, 0.42, 0.50, 0.58, 0.66, 0.74, 0.82, 0.90)]
    gaps = [baselines[i + 1] - baselines[i] for i in range(len(baselines) - 1)]
    line_h = int(np.median(gaps)) if gaps else int(height * 0.045)
    left = mm(request.dpi, 22) if direction != "rtl" else mm(request.dpi, 14)
    right = width - mm(request.dpi, 14) if direction != "rtl" else width - mm(request.dpi, 22)
    page = PageGeometry(
        image=image,
        kind="flow",
        left=left,
        right=right,
        top=baselines[0],
        bottom=baselines[-1] + line_h,
        line_height=line_h,
        baseline_offset=0,
    )
    return page, baselines, line_h


def cv2_rgb(image) -> np.ndarray:
    import cv2

    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def _x_height(template_id: str, line_h: int, style: HandwritingStyle, photo: bool) -> float:
    if photo:
        return max(8.0, line_h * float(np.clip(style.stats.x_height_ratio, 0.3, 0.6)))
    if template_id == "four-line":
        return max(8.0, line_h * 0.30)
    return max(8.0, line_h * 0.42)


def _pieces(fonts, style, text, language, x_height, request, rgb):
    pieces = []
    for index, raw in enumerate(segment(text)):
        if raw == "\n":
            continue
        if raw.strip() == "":
            pieces.append({"kind": "space", "width": x_height * style.stats.word_spacing, "text": raw})
            continue
        if _covered(style, raw):
            width = 0.0
            chars = []
            for ch in raw:
                if ch == " ":
                    advance = x_height * style.stats.word_spacing
                    chars.append((ch, advance, None))
                else:
                    advance = x_height * (_median_width(style, ch) + style.stats.letter_spacing)
                    chars.append((ch, advance, ch))
                width += advance
            pieces.append({"kind": "glyphs", "width": width, "text": raw, "chars": chars, "index": index})
            continue
        font_id = fonts.pick_font(raw, language)
        if dominant_script(raw) in {"Latn", "Zyyy"} and fonts.library.covers(style.fallback_font, raw):
            font_id = style.fallback_font
        px = max(10.0, x_height / 0.48)
        glyphs = fonts.library.shape(font_id, raw, px)
        config = fonts.registry.font(font_id)
        amount = style.stats.jitter_amount if config.jitter == "glyph" else config.jitter_amount
        apply_jitter(glyphs, config.jitter, amount, px, rng_for(style.id, request.language_id, str(index), raw))
        if config.jitter == "glyph" and style.stats.slant_deg:
            lean = style.stats.slant_deg * 0.35
            for glyph in glyphs:
                glyph.rotation += lean
        pieces.append(
            {
                "kind": "font",
                "width": measure_width(glyphs),
                "text": raw,
                "glyphs": glyphs,
                "px": px,
                "index": index,
            }
        )
    return pieces


def _width_of(fonts, style, text, language, x_height, request, rgb) -> float:
    return sum(p["width"] for p in _pieces(fonts, style, text, language, x_height, request, rgb))


def _take(fonts, style, text, language, budget, x_height, request, rgb):
    pieces = _pieces(fonts, style, text, language, x_height, request, rgb)
    if not pieces:
        return [], ""
    chosen = []
    width = 0.0
    consumed = 0
    built = ""
    for piece in pieces:
        if chosen and width + piece["width"] > budget:
            break
        chosen.append(piece)
        width += piece["width"]
        built += piece["text"]
        consumed += len(piece["text"])
        if width > budget:
            break
    # `segment` may not consume the string 1:1 if we only stored piece text.
    # Reconstruct the remainder from the original by the joined piece text.
    if built and text.startswith(built):
        return chosen, text[len(built) :]
    if not chosen:
        return [pieces[0]], text[len(pieces[0]["text"]) :]
    return chosen, text[len(built) :]


def _draw_line(fonts, page, pieces, baseline, indent, language, style, x_height, rgb, alpha, request, photo, para_index):
    if not pieces:
        return
    overlay = Image.new("RGBA", page.image.size, (0, 0, 0, 0))
    if language.direction == "rtl":
        pen = page.right - indent
        ordered = pieces
        # Place from the right, but draw each piece in its own box.
        widths = [p["width"] for p in ordered]
        cursor = pen
        placed = []
        for piece, width in zip(ordered, widths):
            cursor -= width
            placed.append((piece, cursor))
    else:
        cursor = page.left + indent
        placed = []
        for piece in pieces:
            placed.append((piece, cursor))
            cursor += piece["width"]
    for piece, origin in placed:
        if piece["kind"] == "space":
            continue
        if piece["kind"] == "glyphs":
            x = origin
            for offset, (ch, advance, _) in enumerate(piece["chars"]):
                if ch == " " or not style.has_char(ch):
                    x += advance
                    continue
                rng = rng_for(style.id, str(para_index), str(piece["index"]), str(offset), ch)
                variants = style.glyphs[ch]
                variant = variants[rng.randrange(len(variants))]
                jitter = 1 + rng.uniform(-0.05, 0.05)
                y_shift = rng.uniform(-0.04, 0.04) * x_height
                raster = _raster(variant, x_height, jitter)
                if raster is None:
                    x += advance
                    continue
                mask, base, left = raster
                _blit(overlay, mask, int(x + left), int(baseline - base + y_shift), rgb, alpha)
                x += advance
            continue
        draw_glyphs(overlay, piece["glyphs"], origin, baseline, piece["px"], fonts.library, rgb, alpha)
    if photo:
        _multiply(page.image, overlay)
    else:
        page.image.alpha_composite(overlay)


def _header(fonts, page, request, language, rgb, alpha, photo):
    if photo is not None:
        return
    ink = {"rgb": rgb, "alpha": alpha}
    px = max(16.0, page.line_height * 0.45)
    fonts._draw_header(page, request, language, px, ink)


def _number(fonts, page, number, dpi):
    fonts._stamp_page_number(page, number, dpi)
