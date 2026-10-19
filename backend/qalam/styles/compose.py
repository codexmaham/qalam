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
from qalam.renderer.templates import PageGeometry, a4_px, make_page
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


def _inkify(overlay: Image.Image) -> Image.Image:
    """Break a flat font fill into pen ink: grain, a few thin spots, a harder edge.

    Thin strokes stay dark. Grain and a sparse gap pattern sit inside the
    stroke, and the soft halo loses some pixels so the edge is not a perfect
    outline. The pattern depends only on the page size.
    """

    arr = np.array(overlay)
    alpha = arr[:, :, 3].astype(np.float32) / 255.0
    height, width = alpha.shape
    ys, xs = np.indices((height, width))
    grain = ((xs * 17 + ys * 13) % 29) / 28.0
    # Antialiased stems are only partly covered. Lift the body toward solid
    # ink, then let grain and a few gaps break the flat fill.
    core = np.clip((alpha - 0.04) / 0.62, 0.0, 1.0) ** 0.8
    textured = core * (0.84 + 0.16 * grain)
    gap = ((xs * 5 + ys * 3) % 17 == 0) & (((xs * 3 + ys * 11) % 13) > 8) & (alpha > 0.3)
    textured = np.where(gap, textured * 0.4, textured)
    fringe = (alpha > 0.02) & (alpha < 0.22)
    drop = fringe & (((xs + ys * 3) % 3) == 0)
    textured = np.where(drop, 0.0, textured)
    arr[:, :, 3] = np.clip(textured * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def _multiply(page: Image.Image, overlay: Image.Image) -> None:
    base = np.array(page).astype(np.float32)
    over = np.array(overlay).astype(np.float32)
    alpha = over[:, :, 3:4] / 255.0
    ink = over[:, :, :3]
    paper = base[:, :, :3]
    mixed = paper * (1 - alpha) + (paper * ink / 255.0) * alpha
    base[:, :, :3] = mixed
    page.paste(Image.fromarray(base.astype(np.uint8), "RGBA"))


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

    if photo is not None and request.ink_id == "sample" and photo.pen_rgb:
        rgb = photo.pen_rgb
        alpha = 0.94
    elif request.ink_id == "sample":
        rgb = style.stats.ink_rgb
        alpha = 0.94
    else:
        ink = ink_by_id(request.ink_id)
        rgb = ink["rgb"]
        alpha = ink["alpha"]

    pages: list[Image.Image] = []
    line_mm = fonts.registry.font(language.font).line_mm
    page, slots, line_h = _open_page(request, language.direction, photo, line_mm)
    if photo is not None and not slots:
        rgb_page = page.image.convert("RGB")
        return RenderResult(
            pages=[rgb_page],
            truncated=bool(text.strip()),
            width=rgb_page.width,
            height=rgb_page.height,
        )
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
        _number(fonts, page, len(pages) + 1, request.dpi, photo)
        pages.append(page.image)
        page, slots, line_h = _open_page(request, language.direction, photo, line_mm)
        if not slots:
            overflow = True
            return False
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
        _number(fonts, page, len(pages) + 1, request.dpi, photo)
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
    pitch = photo.pitch
    if pitch <= 0 and len(photo.lines) >= 2:
        pitch = float(np.median(np.diff(photo.lines)))
    if pitch <= 0:
        pitch = 0.045
    # Size comes from the rule pitch, not from the gap between the empty lines we keep.
    line_h = max(8, int(round(pitch * height)))
    occupied = photo.occupied if len(photo.occupied) == len(photo.lines) else [False] * len(photo.lines)
    # Only lines that are actually empty. A full page stays blank.
    chosen = [y for y, taken in zip(photo.lines, occupied) if not taken and 0.03 < y < 0.975]
    baselines = []
    for y in chosen:
        row = int(round(y * height))
        if not baselines or row - baselines[-1] > 2:
            baselines.append(row)
    gap = max(8, int(round(line_h * 0.22)))
    if direction != "rtl":
        if 0.04 < photo.margin_x < 0.45:
            left = int(round(photo.margin_x * width)) + gap
        else:
            left = int(round(width * 0.09))
        right = width - int(round(width * 0.06))
    else:
        if photo.margin_x > 0.55:
            right = int(round(photo.margin_x * width)) - gap
        else:
            right = width - int(round(width * 0.09))
        left = int(round(width * 0.06))
    if right - left < line_h * 4:
        left, right = int(width * 0.08), int(width * 0.92)
    if not baselines:
        page = PageGeometry(
            image=image,
            kind="flow",
            left=left,
            right=right,
            top=0,
            bottom=0,
            line_height=line_h,
            baseline_offset=0,
        )
        return page, [], line_h
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
        # Fit the x-height between the rules, leaving room for ascenders and descenders.
        ratio = float(np.clip(style.stats.x_height_ratio, 0.34, 0.46))
        return max(8.0, line_h * ratio)
    if template_id == "four-line":
        return max(8.0, line_h * 0.30)
    return max(8.0, line_h * 0.42)


_EM_X_HEIGHT: dict[str, float] = {}


def _font_px(fonts, font_id: str, x_height: float) -> float:
    """Point size whose rendered x matches `x_height`, not a guessed em ratio."""

    ratio = _EM_X_HEIGHT.get(font_id)
    if ratio is None:
        import freetype

        face = fonts.library.prepare_freetype(font_id, 96.0)
        index = face.get_char_index(ord("x")) or face.get_char_index(ord("o"))
        ratio = 0.47
        if index:
            face.load_glyph(index, freetype.FT_LOAD_NO_HINTING)
            measured = float(face.glyph.metrics.height) / 64.0
            if measured > 2:
                ratio = measured / 96.0
        _EM_X_HEIGHT[font_id] = ratio
    return max(8.0, x_height / max(ratio, 0.2))


def _pieces(fonts, style, text, language, x_height, request, rgb):
    pieces = []
    for index, raw in enumerate(segment(text)):
        if raw == "\n":
            continue
        if raw.strip() == "":
            pieces.append({"kind": "space", "width": x_height * style.stats.word_spacing, "text": raw})
            continue
        letters = [ch for ch in raw if not ch.isspace()]
        use_glyphs = (
            style.engine == "glyphs"
            and letters
            and dominant_script(raw) in {"Latn", "Zyyy"}
            and any(style.has_char(ch) for ch in letters)
        )
        if use_glyphs:
            width = 0.0
            chars = []
            for offset, ch in enumerate(raw):
                if ch.isspace():
                    advance = x_height * style.stats.word_spacing
                    chars.append((ch, advance, None))
                elif style.has_char(ch):
                    advance = x_height * (_median_width(style, ch) + style.stats.letter_spacing)
                    chars.append((ch, advance, "glyph"))
                else:
                    shaped, px, advance = _shape_char(
                        fonts, style, ch, language, x_height, request, f"{index}:{offset}"
                    )
                    chars.append((ch, advance, {"glyphs": shaped, "px": px}))
                width += advance
            pieces.append({"kind": "glyphs", "width": width, "text": raw, "chars": chars, "index": index})
            continue
        font_id = fonts.pick_font(raw, language)
        if dominant_script(raw) in {"Latn", "Zyyy"} and fonts.library.covers(style.fallback_font, raw):
            font_id = style.fallback_font
        px = _font_px(fonts, font_id, x_height)
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
            for offset, (ch, advance, payload) in enumerate(piece["chars"]):
                if ch.isspace() or payload is None:
                    x += advance
                    continue
                rng = rng_for(style.id, str(para_index), str(piece["index"]), str(offset), ch)
                y_shift = rng.uniform(-0.025, 0.025) * x_height
                if payload == "glyph" and style.has_char(ch):
                    variants = style.glyphs[ch]
                    variant = variants[rng.randrange(len(variants))]
                    span = 0.09 if photo else 0.035
                    jitter = 1 + rng.uniform(-span, span)
                    raster = _raster(variant, x_height, jitter)
                    if raster is not None:
                        mask, base, left = raster
                        _blit(overlay, mask, int(x + left), int(baseline - base + y_shift), rgb, alpha)
                elif isinstance(payload, dict):
                    draw_glyphs(
                        overlay,
                        payload["glyphs"],
                        x,
                        baseline + y_shift,
                        payload["px"],
                        fonts.library,
                        rgb,
                        alpha,
                    )
                x += advance
            continue
        if photo:
            rng = rng_for(style.id, "pen", str(para_index), str(piece.get("index", 0)), piece["text"])
            for glyph in piece["glyphs"]:
                glyph.scale *= rng.uniform(0.90, 1.10)
        draw_glyphs(overlay, piece["glyphs"], origin, baseline, piece["px"], fonts.library, rgb, alpha)
    if photo:
        _multiply(page.image, _inkify(overlay))
    else:
        page.image.alpha_composite(overlay)


def _shape_char(fonts, style, ch, language, x_height, request, salt: str):
    font_id = style.fallback_font
    if not fonts.library.covers(font_id, ch):
        font_id = fonts.pick_font(ch, language)
    px = _font_px(fonts, font_id, x_height)
    glyphs = fonts.library.shape(font_id, ch, px)
    config = fonts.registry.font(font_id)
    amount = style.stats.jitter_amount if config.jitter == "glyph" else config.jitter_amount
    apply_jitter(
        glyphs,
        config.jitter,
        min(amount, 0.45),
        px,
        rng_for(style.id, request.language_id, salt, ch),
    )
    if config.jitter == "glyph" and style.stats.slant_deg:
        lean = style.stats.slant_deg * 0.35
        for glyph in glyphs:
            glyph.rotation += lean
    return glyphs, px, measure_width(glyphs)


def _header(fonts, page, request, language, rgb, alpha, photo):
    if photo is not None:
        return
    ink = {"rgb": rgb, "alpha": alpha}
    px = max(16.0, page.line_height * 0.45)
    fonts._draw_header(page, request, language, px, ink)


def _number(fonts, page, number, dpi, photo):
    # A page number is a clean font and can land on ink. The photo is the page.
    if photo is not None:
        return
    fonts._stamp_page_number(page, number, dpi)
