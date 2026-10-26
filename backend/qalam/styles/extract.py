"""Turn a handwriting photo into contours and a few measurements.

The reliable path is the guided template: one letter in each box, so the
label is known. A photo of ordinary notes can be labeled too, when the
user types the transcript. Lines are found, then each line is cut into
the characters of that transcript using the relative widths of the
fallback font, snapped onto the quiet gaps in the ink. Cursive joins and
a wrong transcript both produce rough cuts. Those letters are kept only
when the piece looks like a letter; everything else falls back to a font.

Nothing here needs a GPU or a network. OpenCV and NumPy are wheels.
"""

from __future__ import annotations

import math
from collections import defaultdict

import cv2
import numpy as np
from PIL import ImageFont

from qalam.styles.model import GlyphVariant, HandwritingStyle, StyleStats

SHORT = set("acemnorsuvwxz")
ASCENDER = set("bdfhklt")
MAX_SIDE = 1600


def read_image(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("That file is not an image the notebook can read.")
    return _limit(image)


def _limit(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    scale = MAX_SIDE / max(height, width)
    if scale < 0.99:
        image = cv2.resize(
            image,
            (int(round(width * scale)), int(round(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    elif scale > 1.4:
        image = cv2.resize(
            image,
            (int(round(width * scale)), int(round(height * scale))),
            interpolation=cv2.INTER_CUBIC,
        )
    return image


def ink_mask(image: np.ndarray) -> np.ndarray:
    """Dark strokes and ballpoint, without the red margin or the ruled lines."""

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hue, sat = hsv[:, :, 0], hsv[:, :, 1]
    kernel = max(31, (min(image.shape[:2]) // 12) | 1)
    paper = cv2.morphologyEx(
        gray,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel, kernel)),
    )
    norm = cv2.divide(gray, paper, scale=255)
    strokes = cv2.adaptiveThreshold(
        norm,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        35,
        9,
    )
    red = ((hue < 12) | (hue > 168)) & (sat > 80)
    strokes[red] = 0
    bar = max(28, strokes.shape[1] // 12)
    rules = cv2.morphologyEx(
        strokes,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (bar, 1)),
    )
    strokes[cv2.dilate(rules, np.ones((2, 3), np.uint8)) > 0] = 0
    strokes = cv2.morphologyEx(strokes, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    return strokes


def _advances(font_path: str) -> dict[str, float]:
    font = ImageFont.truetype(font_path, 120)
    table: dict[str, float] = {}
    for code in range(32, 127):
        ch = chr(code)
        box = font.getbbox(ch)
        table[ch] = max(8.0, float(box[2] - box[0]))
    table[" "] = table.get("n", 40) * 0.48
    return table


def find_lines(mask: np.ndarray, count: int | None) -> list[tuple[int, int]]:
    """Horizontal bands of handwriting. `count` is the transcript's line count."""

    proj = (mask > 0).sum(axis=1).astype(np.float32)
    smooth = cv2.GaussianBlur(proj.reshape(-1, 1), (1, 9), 0).ravel()
    width = mask.shape[1]
    best: tuple | None = None
    target = count or 0
    for pct in np.linspace(0.004, 0.09, 28):
        thr = max(3.0, width * float(pct))
        on = smooth > thr
        bands: list[list[int]] = []
        start = None
        for index, value in enumerate(on):
            if value and start is None:
                start = index
            elif not value and start is not None:
                if index - start >= 8:
                    bands.append([start, index])
                start = None
        if start is not None and len(on) - start >= 8:
            bands.append([start, len(on)])
        if not bands:
            continue
        heights = [band[1] - band[0] for band in bands]
        median = float(np.median(heights)) or 1.0
        varied = float(np.mean([(h - median) ** 2 for h in heights])) / (median ** 2)
        err = abs(len(bands) - target) if target else 0
        rank = (err, varied, -sum(heights))
        if best is None or rank < best[0]:
            best = (rank, [band[:] for band in bands], smooth)
    if best is None:
        return []
    bands = best[1]
    smooth = best[2]
    if target:
        while len(bands) > target and len(bands) > 1:
            gaps = [(bands[i + 1][0] - bands[i][1], i) for i in range(len(bands) - 1)]
            _, index = min(gaps)
            bands[index][1] = bands[index + 1][1]
            del bands[index + 1]
        guard = 0
        while len(bands) < target and guard < 24:
            guard += 1
            index = int(np.argmax([band[1] - band[0] for band in bands]))
            top, bot = bands[index]
            if bot - top < 24:
                break
            lo = top + int((bot - top) * 0.28)
            hi = bot - int((bot - top) * 0.28)
            if hi <= lo:
                break
            cut = lo + int(np.argmin(smooth[lo:hi]))
            if cut <= top + 6 or cut >= bot - 6:
                break
            bands[index : index + 1] = [[top, cut], [cut, bot]]
    return [(int(a), int(b)) for a, b in bands]


def _densest_window(mask: np.ndarray, height: int) -> tuple[int, int]:
    """The horizontal strip most likely to be the writing, not a stack of rules."""

    rows = (mask > 0).sum(axis=1).astype(np.float32)
    width = mask.shape[1]
    rows[rows > width * 0.65] = 0
    if mask.shape[0] <= height or height < 8:
        ink = np.where(rows > 0)[0]
        if len(ink) < 2:
            return 0, mask.shape[0]
        return int(ink[0]), int(ink[-1] + 1)
    score = np.convolve(rows, np.ones(height, dtype=np.float32), mode="valid")
    start = int(score.argmax())
    return start, start + height


def _cuts(text: str, column: np.ndarray, advances: dict[str, float]) -> list[int] | None:
    weights = [advances.get(ch, advances.get("n", 40)) for ch in text]
    total = sum(weights) or 1.0
    width = len(column)
    if width < 8:
        return None
    bounds = [0.0]
    acc = 0.0
    for weight in weights:
        acc += weight
        bounds.append(acc / total * width)
    snapped = [0]
    for index in range(1, len(bounds) - 1):
        guess = int(round(bounds[index]))
        letter = max(3, int(round(bounds[index] - bounds[index - 1])))
        window = max(2, int(letter * 0.38))
        lo = max(snapped[-1] + 1, guess - window)
        hi = min(width - 2, guess + window)
        if hi <= lo:
            snap = min(width - 2, snapped[-1] + 1)
        else:
            snap = lo + int(np.argmin(column[lo : hi + 1]))
        snapped.append(max(int(snap), snapped[-1] + 1))
    snapped.append(width)
    return snapped


def _vectorize(mask: np.ndarray, baseline: int, x_height: float) -> tuple[list, list, float]:
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    outers: list[list[list[float]]] = []
    holes: list[list[list[float]]] = []
    if hierarchy is None:
        return [], [], 0.0
    for index, contour in enumerate(contours):
        if cv2.contourArea(contour) < 8:
            continue
        epsilon = 0.015 * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, max(0.8, epsilon), True)
        points = []
        for point in approx[:, 0]:
            x = float(point[0]) / x_height
            y = (baseline - float(point[1])) / x_height
            points.append([round(x, 3), round(y, 3)])
        if len(points) < 3:
            continue
        parent = int(hierarchy[0][index][3])
        if parent >= 0:
            holes.append(points)
        else:
            outers.append(points)
    if not outers:
        return [], [], 0.0
    xs = [p[0] for ring in outers for p in ring]
    width = max(xs) - min(xs) if xs else 0.0
    return outers, holes, max(0.15, width)


def _slant_deg(mask: np.ndarray) -> float | None:
    ys, xs = np.where(mask > 0)
    if len(xs) < 20:
        return None
    top = np.percentile(ys, 18)
    bot = np.percentile(ys, 82)
    if bot - top < 6:
        return None
    x_top = float(np.median(xs[ys <= top]))
    x_bot = float(np.median(xs[ys >= bot]))
    return math.degrees(math.atan2(x_top - x_bot, float(bot - top)))


def _stroke_ratio(mask: np.ndarray, x_height: float) -> float | None:
    dist = cv2.distanceTransform((mask > 0).astype(np.uint8), cv2.DIST_L2, 3)
    ink = dist[mask > 0]
    if ink.size < 10 or x_height <= 1:
        return None
    return float(np.median(ink.astype(np.float64)) * 2.0 / x_height)


def analyse(
    image: np.ndarray,
    *,
    style_id: str,
    name: str,
    description: str,
    fallback_font: str,
    font_path: str,
    transcript: str = "",
    sources: list[str] | None = None,
) -> HandwritingStyle:
    """Label letters from `transcript` (one visual line per line of text)."""

    mask = ink_mask(image)
    advances = _advances(font_path)
    lines = [line for line in transcript.replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    bands = find_lines(mask, len(lines) if lines else None)
    if lines and len(bands) > len(lines):
        bands = bands[: len(lines)]
    glyphs: dict[str, list[GlyphVariant]] = defaultdict(list)
    slants: list[float] = []
    strokes: list[float] = []
    letter_gaps: list[float] = []
    word_gaps: list[float] = []
    x_heights: list[float] = []
    pitches: list[float] = []
    colours: list[np.ndarray] = []

    heights = [b - a for a, b in bands] or [40]
    typical = float(np.median(sorted(heights)[: max(1, len(heights) // 2 + 1)]))
    window = int(np.clip(typical, 28, 110))

    previous_base = None
    for index, (top, bot) in enumerate(bands):
        if index >= len(lines):
            break
        text = lines[index]
        local_top, local_bot = _densest_window(mask[top:bot], window)
        a = top + local_top
        b = top + local_bot
        band = mask[a:b]
        column = (band > 0).sum(axis=0).astype(np.float32)
        xs = np.where(column > 0)[0]
        if len(xs) < 6:
            continue
        x0, x1 = int(xs[0]), int(xs[-1] + 1)
        cuts = _cuts(text, column[x0:x1], advances)
        if cuts is None:
            continue
        boxes = []
        for char_index, ch in enumerate(text):
            if ch == " ":
                continue
            left, right = cuts[char_index], cuts[char_index + 1]
            if right - left < 2:
                continue
            piece = band[:, x0 + left : x0 + right]
            rows = np.where(piece.any(axis=1))[0]
            cols = np.where(piece.any(axis=0))[0]
            if len(rows) < 2 or len(cols) < 1:
                continue
            boxes.append((ch, left + int(cols[0]), left + int(cols[-1]) + 1, int(rows[0]), int(rows[-1]) + 1))
        if not boxes:
            continue
        short_bottoms = [y1 for ch, _, _, _, y1 in boxes if ch.lower() in SHORT]
        baseline = int(np.median(short_bottoms or [y1 for *_, y1 in boxes]))
        heights_x = [baseline - y0 for ch, _, _, y0, _ in boxes if ch.lower() in SHORT and baseline > y0 + 2]
        x_height = float(np.median(heights_x)) if heights_x else max(8.0, (b - a) * 0.45)
        x_height = max(6.0, x_height)
        x_heights.append(x_height)
        if previous_base is not None:
            pitches.append(abs((a + baseline) - previous_base))
        previous_base = a + baseline
        kept_right = None
        for ch, xa, xb, y0, y1 in boxes:
            crop = band[max(0, y0 - 1) : min(band.shape[0], y1 + 1), x0 + xa : x0 + xb]
            if crop.size == 0 or int(crop.sum()) < 80:
                continue
            base_in = baseline - max(0, y0 - 1)
            outers, holes, width = _vectorize(crop, base_in, x_height)
            if not outers or width < 0.12 or width > 3.2:
                continue
            glyphs[ch].append(GlyphVariant(width=width, outers=outers, holes=holes))
            colour = image[a + max(0, y0 - 1) : a + min(band.shape[0], y1 + 1), x0 + xa : x0 + xb]
            sel = crop > 0
            if sel.any() and colour.shape[:2] == sel.shape:
                colours.append(np.percentile(colour[sel], 18, axis=0))
            if ch.lower() in ASCENDER | SHORT:
                angle = _slant_deg(crop)
                if angle is not None and abs(angle) < 35:
                    slants.append(angle)
            stroke = _stroke_ratio(crop, x_height)
            if stroke is not None and 0.02 < stroke < 0.5:
                strokes.append(stroke)
            if kept_right is not None:
                gap = (xa - kept_right) / x_height
                # The previous character in `boxes` is the previous non-space.
                # Word gaps are recorded separately below.
                letter_gaps.append(gap)
            kept_right = xb
        # Word gaps: distance across each space in the transcript.
        nonspace = list(boxes)
        box_i = 0
        prev_right = None
        for ch in text:
            if ch == " ":
                if prev_right is not None and box_i < len(nonspace):
                    word_gaps.append((nonspace[box_i][1] - prev_right) / x_height)
                continue
            if box_i >= len(nonspace):
                break
            prev_right = nonspace[box_i][2]
            box_i += 1

    median_x = float(np.median(x_heights)) if x_heights else 1.0
    # Drop variants taken from a band whose x-height is an outlier.
    # Rebuilding is unnecessary: each variant was normalized by its own
    # x-height, so a wild band still produces a usable shape. We only drop
    # empties, which `_vectorize` already refused.

    ink = (30, 30, 36)
    if colours:
        # OpenCV is BGR. Take a dark percentile so paper at the stroke edge
        # does not wash the pen out.
        bgr = np.median(np.stack(colours), axis=0)
        ink = (int(bgr[2]), int(bgr[1]), int(bgr[0]))
        if sum(ink) / 3 > 150:
            ink = tuple(int(c * 0.55) for c in ink)  # type: ignore[assignment]

    slant = float(np.median(slants)) if slants else 0.0
    letter = float(np.median([g for g in letter_gaps if -0.05 < g < 0.8])) if letter_gaps else 0.14
    word = float(np.median([g for g in word_gaps if 0.1 < g < 2.5])) if word_gaps else max(0.45, letter * 3)
    stroke_w = float(np.median(strokes)) if strokes else 0.12
    pitch = float(np.median([p for p in pitches if p > 8])) if pitches else 0.0
    ratio = float(np.clip((median_x / pitch) if pitch else 0.46, 0.28, 0.62))
    jitter = float(np.clip(0.4 + min(0.45, abs(slant) / 28.0), 0.35, 1.0))
    stats = StyleStats(
        slant_deg=slant,
        x_height_ratio=ratio,
        letter_spacing=float(np.clip(letter, 0.0, 0.45)),
        word_spacing=float(np.clip(word, 0.25, 1.4)),
        stroke_width=float(np.clip(stroke_w, 0.04, 0.35)),
        ink_rgb=ink,  # type: ignore[arg-type]
        jitter_amount=jitter,
    )
    return HandwritingStyle(
        id=style_id,
        name=name,
        description=description,
        fallback_font=fallback_font,
        kind="sample",
        sources=list(sources or []),
        stats=stats,
        glyphs=dict(glyphs),
        note="Letters were cut from a photo using the transcript. Joined writing is approximate.",
    )


def ink_from_image(image: np.ndarray) -> tuple[int, int, int]:
    mask = ink_mask(image)
    sel = mask > 0
    if not sel.any():
        return (30, 30, 36)
    bgr = np.percentile(image[sel], 18, axis=0)
    ink = (int(bgr[2]), int(bgr[1]), int(bgr[0]))
    if sum(ink) / 3 > 150:
        ink = (int(ink[0] * 0.55), int(ink[1] * 0.55), int(ink[2] * 0.55))
    return ink


def merge_styles(styles: list[HandwritingStyle], *, style_id: str, name: str, description: str) -> HandwritingStyle:
    glyphs: dict[str, list[GlyphVariant]] = defaultdict(list)
    for style in styles:
        for ch, variants in style.glyphs.items():
            glyphs[ch].extend(variants)
    # Cap variants so one letter cannot dominate the file or the picker.
    glyphs = {ch: variants[:8] for ch, variants in glyphs.items()}
    base = styles[0]
    slants = [s.stats.slant_deg for s in styles]
    inks = np.mean([s.stats.ink_rgb for s in styles], axis=0)
    stats = StyleStats(
        slant_deg=float(np.median(slants)),
        x_height_ratio=float(np.median([s.stats.x_height_ratio for s in styles])),
        letter_spacing=float(np.median([s.stats.letter_spacing for s in styles])),
        word_spacing=float(np.median([s.stats.word_spacing for s in styles])),
        stroke_width=float(np.median([s.stats.stroke_width for s in styles])),
        ink_rgb=(int(inks[0]), int(inks[1]), int(inks[2])),
        jitter_amount=float(np.median([s.stats.jitter_amount for s in styles])),
    )
    return HandwritingStyle(
        id=style_id,
        name=name,
        description=description,
        fallback_font=base.fallback_font,
        kind="sample",
        sources=[src for style in styles for src in style.sources],
        stats=stats,
        glyphs=glyphs,
        note=base.note,
    )
