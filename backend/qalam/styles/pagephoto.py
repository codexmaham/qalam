"""Straighten a photo of a notebook page and find the lines it was ruled with.

The page becomes the background. Handwriting is drawn on the detected
rules and multiplied into the photo, so the paper texture stays.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

def _decode(data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not read that image")
    height, width = image.shape[:2]
    scale = 1600 / max(height, width)
    if scale < 1:
        image = cv2.resize(
            image,
            (int(round(width * scale)), int(round(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    return image


@dataclass
class PreparedPage:
    image: np.ndarray  # BGR, straightened
    lines: list[float]  # baseline y, 0..1 of the image height
    found_page: bool
    occupied: list[bool] = field(default_factory=list)  # same length as lines
    pitch: float = 0.0  # rule spacing, as a fraction of the image height
    pen_rgb: tuple[int, int, int] | None = None
    margin_x: float = 0.0  # red margin, as a fraction of the width. 0 means none.
    ruled: bool = False
    note: str = ""

    def png_bytes(self) -> bytes:
        ok, buf = cv2.imencode(".png", self.image)
        if not ok:
            raise RuntimeError("Could not encode the page photo")
        return buf.tobytes()


def _order_quad(points: np.ndarray) -> np.ndarray:
    pts = points.reshape(4, 2).astype(np.float32)
    total = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).ravel()
    ordered = np.zeros((4, 2), np.float32)
    ordered[0] = pts[np.argmin(total)]
    ordered[2] = pts[np.argmax(total)]
    ordered[1] = pts[np.argmin(diff)]
    ordered[3] = pts[np.argmax(diff)]
    return ordered


def _warp(image: np.ndarray) -> tuple[np.ndarray, bool]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 40, 140)
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    area = image.shape[0] * image.shape[1]
    for contour in contours[:8]:
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
        if len(approx) != 4 or cv2.contourArea(approx) < area * 0.18:
            continue
        quad = _order_quad(approx)
        width = max(
            np.linalg.norm(quad[1] - quad[0]),
            np.linalg.norm(quad[2] - quad[3]),
        )
        height = max(
            np.linalg.norm(quad[3] - quad[0]),
            np.linalg.norm(quad[2] - quad[1]),
        )
        if width < 40 or height < 40:
            continue
        # A page that already fills the frame is left as it is.
        if cv2.contourArea(approx) > area * 0.92:
            return image, False
        dst = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], np.float32)
        matrix = cv2.getPerspectiveTransform(quad, dst)
        warped = cv2.warpPerspective(image, matrix, (int(width), int(height)))
        return warped, True
    return image, False


def _even_lines(count: int = 12) -> list[float]:
    top, bot = 0.16, 0.94
    step = (bot - top) / count
    return [top + step * (i + 1) for i in range(count)]


def _horizontal_rules(image: np.ndarray) -> list[float]:
    """Thin horizontal edges that cross the page. The page border is left out.

    The first returned row is the first real rule. Nothing is invented above it.
    """

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    if height < 48 or width < 48:
        return []
    x0, x1 = int(width * 0.22), int(width * 0.88)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    sobel = np.abs(cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3))[:, x0:x1]
    threshold = float(np.percentile(sobel, 90))
    covered = (sobel > threshold).mean(axis=1)
    rows = np.where(covered > 0.58)[0]
    if len(rows) == 0:
        return []
    groups: list[list[int]] = [[int(rows[0])]]
    for y in rows[1:]:
        if int(y) - groups[-1][-1] <= 3:
            groups[-1].append(int(y))
        else:
            groups.append([int(y)])
    lines: list[float] = []
    limit = max(5, int(height * 0.012))
    for group in groups:
        if group[-1] - group[0] > limit:
            continue
        y = group[int(np.argmax(covered[group]))]
        frac = y / height
        if 0.035 < frac < 0.97:
            lines.append(float(frac))
    # The top and bottom edges of one rule can register twice. Keep one row.
    merged: list[float] = []
    for y in lines:
        if not merged or y - merged[-1] > 0.01:
            merged.append(y)
        else:
            merged[-1] = (merged[-1] + y) / 2
    return [round(y, 5) for y in merged]


def _regular(lines: list[float]) -> tuple[bool, float]:
    if len(lines) < 5:
        return False, 0.0
    gaps = np.diff(np.asarray(lines, dtype=np.float64))
    gaps = gaps[(gaps > 0.012) & (gaps < 0.12)]
    if len(gaps) < 4:
        return False, 0.0
    pitch = float(np.median(gaps))
    close = np.mean(np.abs(gaps - pitch) < pitch * 0.28)
    return bool(close > 0.62), pitch


def _fill_internal(lines: list[float], pitch: float) -> list[float]:
    """Insert a missed rule between two detections. Do not extend past either end."""

    if pitch <= 0 or len(lines) < 2:
        return lines
    filled = [lines[0]]
    for y in lines[1:]:
        gap = y - filled[-1]
        steps = int(round(gap / pitch))
        if steps >= 2 and abs(gap - steps * pitch) < pitch * 0.35:
            for step in range(1, steps):
                filled.append(round(filled[-1] + pitch, 5))
        filled.append(y)
    return filled


def _margin_x(image: np.ndarray) -> float:
    """The red vertical margin, as a fraction of the width. 0 when there is none."""

    blue, green, red = cv2.split(image)
    bi = blue.astype(np.int16)
    gi = green.astype(np.int16)
    ri = red.astype(np.int16)
    red_px = (ri > bi + 24) & (ri > gi + 14) & (red > 85)
    height, width = red_px.shape
    y0, y1 = int(height * 0.08), int(height * 0.92)
    column = red_px[y0:y1].mean(axis=0)
    peak = float(column.max()) if width else 0.0
    if peak < 0.18:
        return 0.0
    xs = np.where(column > peak * 0.65)[0]
    if len(xs) == 0:
        return 0.0
    groups: list[list[int]] = [[int(xs[0])]]
    for x in xs[1:]:
        if int(x) - groups[-1][-1] <= 4:
            groups[-1].append(int(x))
        else:
            groups.append([int(x)])
    best = max(groups, key=lambda group: float(column[group].sum()))
    # A word or a stamp is wide. A margin line is a few pixels.
    if best[-1] - best[0] > width * 0.04:
        return 0.0
    weights = column[best] + 1e-6
    return float(np.average(best, weights=weights) / width)


def _ink_mask(image: np.ndarray) -> np.ndarray:
    """Pen strokes. Rules, the red margin, and paper grain are left out."""

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    paper = cv2.GaussianBlur(gray, (0, 0), max(2.5, height * 0.01))
    darker = paper.astype(np.int16) - gray.astype(np.int16)
    ink = (darker > 24) & (gray < 155)
    blue, green, red = cv2.split(image)
    bi = blue.astype(np.int16)
    gi = green.astype(np.int16)
    ri = red.astype(np.int16)
    red_px = (ri > bi + 22) & (ri > gi + 12) & (red > 80)
    blue_px = (bi > ri + 18) & (bi > gi + 8) & (gray > 90)
    ink = ink & ~red_px & ~blue_px
    mask = ink.astype(np.uint8) * 255
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, 8)
    clean = np.zeros_like(mask)
    min_area = max(8, int(height * width * 0.000012))
    for comp in range(1, count):
        if int(stats[comp, cv2.CC_STAT_AREA]) >= min_area:
            clean[labels == comp] = 255
    bar = max(28, width // 5)
    rules = cv2.morphologyEx(clean, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (bar, 1)))
    clean[cv2.dilate(rules, np.ones((3, 5), np.uint8)) > 0] = 0
    return clean


def _zone_has_ink(ink: np.ndarray, baseline: float, pitch: float, margin_x: float) -> bool:
    """True when pen strokes already fill the writing zone above this baseline."""

    height, width = ink.shape
    y1 = int(round(baseline * height)) - 2
    y0 = int(round((baseline - max(pitch, 0.02)) * height)) + 3
    if y1 - y0 < 4:
        return True
    left = margin_x + 0.025 if margin_x > 0.04 else 0.08
    x0 = int(width * left)
    x1 = int(width * 0.94)
    band = ink[max(0, y0) : max(0, min(height, y1)), max(0, x0) : max(0, x1)]
    if band.size == 0 or band.shape[0] < 3:
        return False
    count = int((band > 0).sum())
    need = max(40, int(band.size * 0.0045))
    if count < need:
        return False
    rows = int((band > 0).any(axis=1).sum())
    return rows >= max(3, int(band.shape[0] * 0.12))


def _text_lines(ink: np.ndarray) -> tuple[list[tuple[float, float]], float]:
    """Handwriting lines as (top, bottom) fractions, plus the line pitch.

    Used when the page has no ruled grid. The pitch is the spacing of the
    writing already on the page, read from peaks in the ink, not from a
    guess that runs off the top.
    """

    height, width = ink.shape
    x0, x1 = int(width * 0.08), int(width * 0.92)
    if x1 <= x0 or height < 16:
        return [], 0.0
    coverage = (ink[:, x0:x1] > 0).astype(np.float64).mean(axis=1)
    smooth = cv2.GaussianBlur(coverage.reshape(-1, 1), (0, 0), max(1.0, height * 0.005)).ravel()
    min_gap = max(4, int(height * 0.02))
    peaks: list[int] = []
    for y in range(2, height - 2):
        if smooth[y] < 0.045:
            continue
        if smooth[y] < smooth[y - 1] or smooth[y] < smooth[y + 1]:
            continue
        if not peaks or y - peaks[-1] > min_gap:
            peaks.append(y)
        elif smooth[y] > smooth[peaks[-1]]:
            peaks[-1] = y
    if not peaks:
        return [], 0.0
    if len(peaks) >= 2:
        gaps = np.diff(np.asarray(peaks))
        likely = gaps[(gaps > height * 0.018) & (gaps < height * 0.12)]
        pitch_px = float(np.median(likely if len(likely) else gaps))
    else:
        pitch_px = max(8.0, height * 0.045)
    bands: list[tuple[float, float]] = []
    for peak in peaks:
        top = peak
        limit = int(pitch_px * 0.8)
        while top > 0 and smooth[top] > 0.016 and peak - top < limit:
            top -= 1
        bottom = peak
        while bottom < height - 1 and smooth[bottom] > 0.016 and bottom - peak < int(pitch_px * 0.65):
            bottom += 1
        bands.append((top / height, (bottom + 1) / height))
    merged: list[tuple[float, float]] = [bands[0]]
    for top, bottom in bands[1:]:
        if top <= merged[-1][1] + 0.004:
            merged[-1] = (merged[-1][0], max(merged[-1][1], bottom))
        else:
            merged.append((top, bottom))
    if len(peaks) == 1 and merged:
        pitch_px = max(pitch_px, (merged[0][1] - merged[0][0]) * height * 1.8)
    return merged, pitch_px / height


def _free_slots(bands: list[tuple[float, float]], pitch: float, ink: np.ndarray, margin_x: float) -> list[float]:
    """Baselines whose whole line is empty, including room below the last ink."""

    if pitch <= 0:
        return []
    free: list[float] = []

    def consider(start: float, limit: float) -> None:
        y = start
        while y < limit:
            if _zone_has_ink(ink, y, pitch, margin_x):
                y += pitch
                continue
            free.append(round(float(y), 5))
            y += pitch

    for (_top, bottom), (next_top, _next_bottom) in zip(bands, bands[1:]):
        if next_top - bottom < pitch * 1.45:
            continue
        consider(bottom + pitch, next_top - pitch * 0.4)
    if bands:
        consider(bands[-1][1] + pitch, 0.985 - pitch * 0.4)
    return free


def _sample_pen(image: np.ndarray, ink: np.ndarray) -> tuple[int, int, int] | None:
    selected = ink > 0
    if int(selected.sum()) < 80:
        return None
    bgr = np.percentile(image[selected], 35, axis=0)
    rgb = (int(np.clip(bgr[2], 0, 255)), int(np.clip(bgr[1], 0, 255)), int(np.clip(bgr[0], 0, 255)))
    # Rule shadows and paper grain are grey, not a pen. Keep the style ink then.
    if sum(rgb) / 3 > 110:
        return None
    return rgb


def _note(lines: list[float], occupied: list[bool], ruled: bool) -> str:
    free = sum(1 for taken in occupied if not taken)
    if free == 0:
        return "No empty line on this page, so nothing new is written."
    if not ruled:
        noun = "line" if free == 1 else "lines"
        return f"No rules on this page. {free} empty {noun} where the paper is clear."
    if free < len(lines):
        return f"{len(lines)} ruled lines, {free} empty. Writing starts on the first free line."
    return f"{len(lines)} ruled lines. Writing sits on the rules, just past the margin."


def prepare_page(data: bytes) -> PreparedPage:
    image = _decode(data)
    warped, found = _warp(image)
    # Cap the working size. The renderer scales this onto A4.
    height, width = warped.shape[:2]
    scale = 1600 / max(height, width)
    if scale < 1:
        warped = cv2.resize(
            warped,
            (int(round(width * scale)), int(round(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    margin = _margin_x(warped)
    rules = _horizontal_rules(warped)
    regular, pitch = _regular(rules)
    ink = _ink_mask(warped)
    ruled = len(rules) >= 5
    if ruled:
        if not regular or pitch <= 0:
            gaps = np.diff(np.asarray(rules, dtype=np.float64))
            gaps = gaps[gaps > 0.012]
            pitch = float(np.median(gaps)) if len(gaps) else 0.04
        lines = _fill_internal(rules, pitch) if regular else list(rules)
        occupied = [_zone_has_ink(ink, y, pitch, margin) for y in lines]
    else:
        bands, band_pitch = _text_lines(ink)
        if not bands:
            lines = _even_lines()
            pitch = lines[1] - lines[0]
            occupied = [False] * len(lines)
        else:
            pitch = band_pitch or 0.045
            lines = [round(band[1], 5) for band in bands]
            occupied = [True] * len(lines)
            for y in _free_slots(bands, pitch, ink, margin):
                lines.append(y)
                occupied.append(False)
            order = np.argsort(np.asarray(lines))
            lines = [lines[int(i)] for i in order]
            occupied = [occupied[int(i)] for i in order]
    pen = _sample_pen(warped, ink)
    # A detected rule is the baseline. Nothing is invented above the first one.
    return PreparedPage(
        image=warped,
        lines=lines,
        found_page=found or ruled,
        occupied=occupied,
        pitch=float(pitch or 0.0),
        pen_rgb=pen,
        margin_x=margin,
        ruled=ruled,
        note=_note(lines, occupied, ruled),
    )
