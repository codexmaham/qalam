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
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    area = image.shape[0] * image.shape[1]
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w < 18 or h < 18:
            continue
        if not 0.65 <= w / h <= 1.45:
            continue
        if w * h < area * 0.0004 or w * h > area * 0.02:
            continue
        boxes.append((x, y, w, h))
    boxes.sort(key=lambda item: (item[1], item[0]))
    kept: list[tuple[int, int, int, int]] = []
    for box in boxes:
        x, y, w, h = box
        duplicate = False
        for ox, oy, ow, oh in kept:
            if abs(x - ox) < w * 0.4 and abs(y - oy) < h * 0.4:
                duplicate = True
                break
        if not duplicate:
            kept.append(box)
    if not kept:
        return []
    widths = sorted(box[2] for box in kept)
    median = widths[len(widths) // 2]
    kept = [box for box in kept if abs(box[2] - median) < median * 0.28 and abs(box[3] - median) < median * 0.45]
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


def analyse_sheet(
    image: np.ndarray,
    *,
    style_id: str,
    name: str,
    font_path: str,
    fallback_font: str = "caveat",
) -> HandwritingStyle:
    """Read a filled template. Boxes are matched to `ORDER` left to right, top to bottom."""

    del font_path  # the sheet's printed labels are outside the boxes
    mask = ink_mask(image)
    cells = _cells(image)
    glyphs: dict[str, list[GlyphVariant]] = {}
    colours = []
    slants_ready = []
    for index, (x, y, w, h) in enumerate(cells):
        if index >= len(ORDER):
            break
        ch = ORDER[index]
        pad = max(2, int(min(w, h) * 0.12))
        crop = mask[y + pad : y + h - pad, x + pad : x + w - pad]
        if crop.size == 0 or (crop > 0).mean() < 0.01:
            continue
        ys, xs = np.where(crop > 0)
        if len(xs) < 8:
            continue
        tight = crop[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
        baseline = tight.shape[0] - max(1, int(tight.shape[0] * 0.08))
        # Sit the baseline under the ink, with a small descent allowance.
        ink_bottom = int(ys.max() - ys.min())
        baseline = ink_bottom
        x_height = max(6.0, tight.shape[0] * 0.72)
        outers, holes, width = _vectorize(tight, baseline, x_height)
        if not outers:
            continue
        glyphs.setdefault(ch, []).append(GlyphVariant(width=width, outers=outers, holes=holes))
        colour = image[y + pad : y + h - pad, x + pad : x + w - pad]
        sel = crop > 0
        if colour.shape[:2] == sel.shape and sel.any():
            colours.append(np.percentile(colour[sel], 18, axis=0))
        ratio = _stroke_ratio(tight, x_height)
        if ratio:
            slants_ready.append(ratio)
    ink = (30, 30, 36)
    if colours:
        bgr = np.median(np.stack(colours), axis=0)
        ink = (int(np.clip(bgr[2], 0, 255)), int(np.clip(bgr[1], 0, 255)), int(np.clip(bgr[0], 0, 255)))
        if sum(ink) / 3 > 150:
            ink = tuple(int(c * 0.55) for c in ink)  # type: ignore[assignment]
    stroke = float(np.median(slants_ready)) if slants_ready else 0.12
    return HandwritingStyle(
        id=style_id,
        name=name,
        description="Your letters, from the Qalam handwriting sheet.",
        fallback_font=fallback_font,
        kind="sample",
        stats=StyleStats(
            ink_rgb=ink,  # type: ignore[arg-type]
            stroke_width=float(np.clip(stroke, 0.04, 0.35)),
            jitter_amount=0.5,
        ),
        glyphs=glyphs,
        note="Read from the guided sheet, one character per box.",
    )
