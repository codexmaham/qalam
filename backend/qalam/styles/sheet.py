"""A printable sheet with one box per character.

Photographing this filled sheet is the path that labels letters correctly.
The character name sits above the box, so the pen inside the box is the
only ink the extractor keeps.
"""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from qalam.styles.extract import _stroke_ratio, _vectorize, ink_mask
from qalam.styles.model import GlyphVariant, HandwritingStyle, StyleStats

# Letters whose body is the x-height. Ascenders and descenders are measured
# against this shared size instead of against their own bounding box.
_X_HEIGHT = set("acemnorsuvwxz")
_ASCENDERS = set("bdfhklt") | set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
_DESCENDERS = set("gjpqy")
_NARROW = set("ilj1")
_WIDE = set("mwMW")

ORDER = (
    list("abcdefghijklm")
    + list("nopqrstuvwxyz")
    + list("ABCDEFGHIJKLM")
    + list("NOPQRSTUVWXYZ")
    + list("0123456789")
    + list(".,'!?-")
)


def render_sheet(font_path: str, dpi: int = 140) -> Image.Image:
    width = int(round(210 / 25.4 * dpi))
    height = int(round(297 / 25.4 * dpi))
    image = Image.new("RGB", (width, height), (255, 252, 246))
    draw = ImageDraw.Draw(image)
    title = ImageFont.truetype(font_path, max(28, int(dpi * 0.42)))
    small = ImageFont.truetype(font_path, max(14, int(dpi * 0.16)))
    draw.text((int(width * 0.08), int(dpi * 0.35)), "Qalam handwriting sheet", font=title, fill=(40, 32, 28))
    draw.text(
        (int(width * 0.08), int(dpi * 0.85)),
        "Write one character in each box, with your usual pen. Leave a box blank to skip it.",
        font=small,
        fill=(90, 80, 70),
    )
    rows = [ORDER[i : i + 13] for i in range(0, len(ORDER), 13)]
    margin = int(width * 0.07)
    top = int(dpi * 1.35)
    usable = width - margin * 2
    box = int(usable / 13)
    gap = max(6, int(dpi * 0.08))
    y = top
    for row in rows:
        for index, ch in enumerate(row):
            x = margin + index * box
            draw.text((x + box * 0.28, y), ch, font=small, fill=(170, 160, 150))
            draw.rectangle((x + 2, y + int(box * 0.38), x + box - 6, y + int(box * 0.38) + box - 10), outline=(40, 40, 40), width=2)
        y += box + gap
    return image


def _cells(image: np.ndarray) -> list[tuple[int, int, int, int]]:
    """The printed boxes, not the grey labels sitting above them."""

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    dark = (gray < 90).astype(np.uint8) * 255
    horiz = cv2.morphologyEx(
        dark,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(14, image.shape[1] // 50), 1)),
    )
    vert = cv2.morphologyEx(
        dark,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(14, image.shape[0] // 60))),
    )
    frames = cv2.dilate(cv2.bitwise_or(horiz, vert), np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(frames, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    area = image.shape[0] * image.shape[1]
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w < 18 or h < 18 or not 0.7 <= w / max(h, 1) <= 1.5:
            continue
        if w * h < area * 0.00025 or w * h > area * 0.025:
            continue
        boxes.append((x, y, w, h))
    boxes.sort(key=lambda item: (item[1], item[0]))
    kept: list[tuple[int, int, int, int]] = []
    for box in boxes:
        x, y, w, h = box
        if any(abs(x - ox) < w * 0.45 and abs(y - oy) < h * 0.45 for ox, oy, _ow, _oh in kept):
            continue
        kept.append(box)
    if not kept:
        return []
    widths = sorted(box[2] for box in kept)
    median = widths[len(widths) // 2]
    kept = [box for box in kept if abs(box[2] - median) < median * 0.28 and abs(box[3] - median) < median * 0.35]
    kept.sort(key=lambda item: item[1])
    rows: list[list[tuple[int, int, int, int]]] = []
    for box in kept:
        if not rows or box[1] - rows[-1][0][1] > box[3] * 0.45:
            rows.append([box])
        else:
            rows[-1].append(box)
    ordered = []
    for row in rows:
        row.sort(key=lambda item: item[0])
        ordered.extend(row)
    return ordered


def _inner(mask: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    """Ink inside a box, with the printed outline removed."""

    x, y, w, h = box
    inset = max(3, int(round(min(w, h) * 0.16)))
    crop = mask[y + inset : y + h - inset, x + inset : x + w - inset].copy()
    if crop.size == 0:
        return crop
    crop[:2, :] = 0
    crop[-2:, :] = 0
    crop[:, :2] = 0
    crop[:, -2:] = 0
    height, width = crop.shape
    if width > 8 and height > 8:
        horiz = cv2.morphologyEx(
            crop,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, (max(8, int(width * 0.7)), 1)),
        )
        vert = cv2.morphologyEx(
            crop,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(8, int(height * 0.7)))),
        )
        crop[cv2.dilate(cv2.bitwise_or(horiz, vert), np.ones((2, 2), np.uint8)) > 0] = 0
    count, labels, stats, _ = cv2.connectedComponentsWithStats((crop > 0).astype(np.uint8), 8)
    for index in range(1, count):
        cx, cy, cw, ch, _area = (int(v) for v in stats[index])
        touches = cx <= 0 or cy <= 0 or cx + cw >= width or cy + ch >= height
        if touches:
            crop[labels == index] = 0
    return crop


def _ink_bounds(crop: np.ndarray) -> tuple[int, int, int, int] | None:
    ys, xs = np.where(crop > 0)
    if len(xs) < 12:
        return None
    return int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())


def _spans(outers: list, holes: list) -> tuple[float, float, float, float]:
    rings = outers + holes
    ys = [point[1] for ring in rings for point in ring]
    xs = [point[0] for ring in outers for point in ring]
    if not ys or not xs:
        return 0.0, 0.0, 0.0, 0.0
    return min(ys), max(ys), min(xs), max(xs)


def _acceptable(
    ch: str,
    outers: list,
    holes: list,
    stroke: float | None,
    median_stroke: float | None,
) -> bool:
    if not outers or len(outers) > 8:
        return False
    bottom, top, left, right = _spans(outers, holes)
    ink_h = top - bottom
    ink_w = right - left
    if ink_h > 2.8 or ink_w > 2.6 or ink_h < 0.08:
        return False
    if stroke and median_stroke and not (0.45 * median_stroke <= stroke <= 2.35 * median_stroke):
        return False
    if ch in _X_HEIGHT:
        return 0.78 <= ink_h <= 1.28 and 0.78 <= top <= 1.28 and -0.22 <= bottom <= 0.2
    if ch in _DESCENDERS:
        return bottom < -0.12 and 0.65 <= top <= 1.45 and 1.05 <= ink_h <= 2.5
    if ch in _ASCENDERS:
        floor = 1.02 if ch in {"t", "i"} else 1.15
        return top >= floor and top <= 2.25 and -0.35 <= bottom <= 0.22
    if ch in _NARROW and not (0.08 <= ink_w <= 0.9):
        return False
    if ch in _WIDE and not (0.62 <= ink_w <= 2.6):
        return False
    return -0.55 <= bottom and top <= 2.15


def write_guide_letters(image: np.ndarray, font_path: str, colour: tuple[int, int, int] = (25, 45, 130)) -> np.ndarray:
    """Draw one character in each detected box, sharing a baseline inside the box."""

    cells = _cells(image)
    if not cells:
        return image
    pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    median_h = int(np.median([box[3] for box in cells]))
    pen = ImageFont.truetype(font_path, max(16, int(median_h * 0.62)))
    ascent, _descent = pen.getmetrics()
    for index, (x, y, w, h) in enumerate(cells[: len(ORDER)]):
        ch = ORDER[index]
        baseline = y + int(h * 0.66)
        box = pen.getbbox(ch)
        glyph_w = box[2] - box[0]
        draw.text((x + max(3, (w - glyph_w) // 2), baseline - ascent), ch, font=pen, fill=colour)
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def analyse_sheet(
    image: np.ndarray,
    *,
    style_id: str,
    name: str,
    font_path: str,
    fallback_font: str = "caveat",
) -> HandwritingStyle:
    """Read a filled template. Boxes are matched to `ORDER` left to right, top to bottom.

    Every kept letter shares one x-height and one baseline, taken from the
    x-height letters (a, c, e, m, …). A contour that is a box edge, a merged
    blob, or the wrong size for its class is dropped so the font can draw it.
    """

    del font_path  # the sheet's printed labels are outside the boxes
    mask = ink_mask(image)
    cells = _cells(image)
    prepared: list[tuple[str, np.ndarray, tuple[int, int]]] = []
    for index, box in enumerate(cells):
        if index >= len(ORDER):
            break
        crop = _inner(mask, box)
        if crop.size == 0:
            continue
        x, y, w, h = box
        inset = max(3, int(round(min(w, h) * 0.16)))
        prepared.append((ORDER[index], crop, (x + inset, y + inset)))

    reference: list[tuple[int, int, int]] = []
    for ch, crop, _origin in prepared:
        if ch not in _X_HEIGHT:
            continue
        bounds = _ink_bounds(crop)
        if bounds is None:
            continue
        top, bottom, left, right = bounds
        if bottom - top > crop.shape[0] * 0.72 or right - left > crop.shape[1] * 0.9:
            continue
        reference.append((bottom - top + 1, bottom, crop.shape[0]))
    glyphs: dict[str, list[GlyphVariant]] = {}
    colours = []
    strokes: list[float] = []
    if len(reference) >= 4:
        heights = sorted(item[0] for item in reference)
        median_h = float(heights[len(heights) // 2])
        kept_ref = [item for item in reference if median_h * 0.75 <= item[0] <= median_h * 1.25]
        if len(kept_ref) < 3:
            kept_ref = reference
        x_height = float(np.median([item[0] for item in kept_ref]))
        base_frac = float(np.median([item[1] / item[2] for item in kept_ref]))
        crop_h = float(np.median([item[2] for item in kept_ref]))
    else:
        x_height = 0.0
        base_frac = 0.72
        crop_h = 1.0

    measured: list[tuple[str, np.ndarray, float, tuple[int, int]]] = []
    for ch, crop, origin in prepared:
        if x_height < 4:
            break
        scale = crop.shape[0] / crop_h if crop_h else 1.0
        local_x = max(4.0, x_height * scale)
        ratio = _stroke_ratio(crop, local_x)
        if ch in _X_HEIGHT and ratio:
            bounds = _ink_bounds(crop)
            if bounds and abs((bounds[1] - bounds[0] + 1) - local_x) <= local_x * 0.28:
                strokes.append(ratio)
        measured.append((ch, crop, local_x, origin))
    median_stroke = float(np.median(strokes)) if strokes else None

    for ch, crop, local_x, origin in measured:
        bounds = _ink_bounds(crop)
        if bounds is None:
            continue
        _top, _bottom, left, right = bounds
        slab = crop[:, left : right + 1]
        baseline = int(round(base_frac * crop.shape[0]))
        stroke = _stroke_ratio(slab, local_x)
        outers, holes, width = _vectorize(slab, baseline, local_x)
        if not _acceptable(ch, outers, holes, stroke, median_stroke):
            continue
        if ch in _NARROW and not (0.08 <= width <= 0.9):
            continue
        if ch in _WIDE and not (0.62 <= width <= 2.6):
            continue
        if ch.isalpha() and ch not in _NARROW | _WIDE and not (0.22 <= width <= 1.85):
            continue
        glyphs.setdefault(ch, []).append(GlyphVariant(width=width, outers=outers, holes=holes))
        ox, oy = origin
        colour = image[oy : oy + crop.shape[0], ox : ox + crop.shape[1]]
        sel = crop > 0
        if colour.shape[:2] == sel.shape and sel.any():
            colours.append(np.percentile(colour[sel], 18, axis=0))
    ink = (30, 30, 36)
    if colours:
        bgr = np.median(np.stack(colours), axis=0)
        ink = (int(np.clip(bgr[2], 0, 255)), int(np.clip(bgr[1], 0, 255)), int(np.clip(bgr[0], 0, 255)))
        if sum(ink) / 3 > 150:
            ink = tuple(int(c * 0.55) for c in ink)  # type: ignore[assignment]
    stroke_value = median_stroke if median_stroke else 0.12
    return HandwritingStyle(
        id=style_id,
        name=name,
        description="Your letters, from the Qalam handwriting sheet.",
        fallback_font=fallback_font,
        kind="sample",
        stats=StyleStats(
            ink_rgb=ink,  # type: ignore[arg-type]
            stroke_width=float(np.clip(stroke_value, 0.04, 0.35)),
            jitter_amount=0.35,
        ),
        glyphs=glyphs,
        note="Letters share one x-height and baseline. A bad contour falls back to the font.",
    )
