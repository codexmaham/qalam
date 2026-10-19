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


def _rules(image: np.ndarray) -> list[float]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    sobel = np.abs(cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3))
    strong = sobel > np.percentile(sobel, 93)
    blue = (hue > 85) & (hue < 140) & (sat > 25) & (val > 80) & (val < 230)
    ink = (strong | blue).astype(np.uint8) * 255
    bar = max(30, image.shape[1] // 7)
    horiz = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (bar, 1)))
    proj = (horiz > 0).sum(axis=1)
    need = image.shape[1] * 0.35
    ys = np.where(proj > need)[0]
    if len(ys) == 0:
        return []
    groups: list[list[int]] = [[int(ys[0])]]
    for y in ys[1:]:
        if y - groups[-1][-1] <= 4:
            groups[-1].append(int(y))
        else:
            groups.append([int(y)])
    lines = [sum(group) / len(group) / image.shape[0] for group in groups if len(group) >= 1]
    # Drop lines that sit on top of each other.
    kept: list[float] = []
    for y in lines:
        if not kept or y - kept[-1] > 0.012:
            kept.append(float(y))
    return kept


def _even_lines(count: int = 12) -> list[float]:
    top, bot = 0.16, 0.94
    step = (bot - top) / count
    return [top + step * (i + 1) for i in range(count)]


def _estimate_pitch(lines: list[float]) -> float | None:
    """The rule spacing, even when some rules were missed and a few are doubled."""

    if len(lines) < 3:
        return None
    gaps = np.diff(np.asarray(lines, dtype=np.float64))
    gaps = gaps[gaps > 0.008]
    if len(gaps) == 0:
        return None
    seeds = [float(g) for g in gaps]
    seeds += [float(g) / 2 for g in gaps if g / 2 > 0.012]
    seeds += [float(g) / 3 for g in gaps if g / 3 > 0.012]
    best_pitch: float | None = None
    best_score = -1e9
    for pitch in seeds:
        explained = 0.0
        residual = 0.0
        for gap in gaps:
            steps = max(1, int(round(float(gap) / pitch)))
            err = abs(float(gap) - steps * pitch) / pitch
            residual += err
            if err < 0.18:
                explained += 1.0
        score = explained - residual * 0.12
        smaller = best_pitch is None or pitch < best_pitch - 1e-4
        if score > best_score + 0.08 or (abs(score - best_score) <= 0.08 and smaller):
            best_score = score
            best_pitch = pitch
    if best_pitch is None or best_score < 1.4:
        return None
    return best_pitch


def _grid(lines: list[float], pitch: float) -> list[float]:
    """Snap detected rules onto one spacing and fill the rules that were missed."""

    if len(lines) < 2 or pitch <= 0:
        return lines
    best_origin = lines[0]
    best_err = 1e9
    for origin in lines:
        err = 0.0
        for y in lines:
            steps = round((y - origin) / pitch)
            err += abs(y - (origin + steps * pitch))
        if err < best_err:
            best_err = err
            best_origin = origin
    if best_err / len(lines) > pitch * 0.28:
        return lines
    first, last = min(lines), max(lines)
    y = best_origin
    while y - pitch >= max(0.04, first - pitch * 0.45):
        y -= pitch
    grid: list[float] = []
    while y <= min(0.98, last + pitch * 0.45):
        if 0.045 < y < 0.975:
            grid.append(round(float(y), 5))
        y += pitch
    return grid or lines


def _periodic_rules(image: np.ndarray) -> tuple[list[float], float | None]:
    """One rule spacing from the repeating horizontal edges, including faint rules."""

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    sobel = np.abs(cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3))
    height, width = gray.shape
    if height < 48:
        return [], None
    profile = sobel[:, int(width * 0.16) : int(width * 0.92)].mean(axis=1)
    signal = profile - float(profile.mean())
    size = len(signal)
    spectrum = np.fft.rfft(signal, n=size * 2)
    corr = np.fft.irfft(spectrum * np.conj(spectrum))[:size]
    lo = max(8, int(height * 0.018))
    hi = max(lo + 4, int(height * 0.09))
    peak = lo + int(np.argmax(corr[lo:hi]))
    if corr[0] <= 1 or float(corr[peak]) / float(corr[0]) < 0.12:
        return [], None
    best_phase = 0
    best_score = -1.0
    for phase in range(peak):
        rows = np.arange(phase, height - 2, peak)
        rows = rows[(rows > height * 0.04) & (rows < height * 0.97)]
        if len(rows) < 5:
            continue
        score = float(np.percentile(profile[rows], 30))
        if score > best_score:
            best_score = score
            best_phase = phase
    lines: list[float] = []
    for y in range(best_phase, height, peak):
        frac = y / height
        if 0.045 < frac < 0.975:
            lines.append(round(float(frac), 5))
    if len(lines) < 5:
        return [], None
    return lines, peak / height


def _pen_ink(image: np.ndarray, pitch: float) -> np.ndarray:
    """Dark pen strokes. Ruled lines and the red margin are left out."""

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    sigma = max(2.0, float(pitch) * gray.shape[0] * 0.42)
    paper = cv2.GaussianBlur(gray, (0, 0), sigma)
    darker = paper.astype(np.int16) - gray.astype(np.int16)
    ink = ((darker > 32) & (gray < 120)).astype(np.uint8) * 255
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hue, sat = hsv[:, :, 0], hsv[:, :, 1]
    blue = (hue > 85) & (hue < 145) & (sat > 18) & (gray > 105)
    red = ((hue < 12) | (hue > 168)) & (sat > 45)
    ink[blue | red] = 0
    bar = max(18, image.shape[1] // 4)
    rules = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (bar, 1)))
    ink[cv2.dilate(rules, np.ones((2, 5), np.uint8)) > 0] = 0
    return ink


def _mark_occupied(image: np.ndarray, lines: list[float], pitch: float) -> list[bool]:
    """A line is taken when letter-shaped pen ink already sits above that rule."""

    if not lines:
        return []
    ink = _pen_ink(image, pitch if pitch > 0 else 0.04)
    height, width = ink.shape
    margin = int(width * 0.16)
    right = int(width * 0.94)
    step = pitch if pitch > 0 else 0.04
    scale = max(0.65, height / 520.0)
    min_height = max(4, int(round(6 * scale)))
    min_piece = max(12, int(round(16 * scale * scale)))
    min_total = max(80, int(round(110 * scale * scale)))
    flags: list[bool] = []
    for index, y in enumerate(lines):
        above = lines[index - 1] if index else y - step
        y0 = int(round(above * height)) + 2
        y1 = int(round(y * height)) - 2
        band = ink[max(0, y0) : max(0, min(height, y1)), margin:right]
        if band.size == 0 or band.shape[0] < 3:
            flags.append(False)
            continue
        count, _labels, stats, _centroids = cv2.connectedComponentsWithStats((band > 0).astype(np.uint8), 8)
        letters = 0
        area = 0
        limit = band.shape[1] * 0.5
        for comp in range(1, count):
            _x, _y, comp_w, comp_h, comp_area = (int(v) for v in stats[comp])
            if comp_h >= min_height and comp_w >= 3 and comp_w < limit and comp_area >= min_piece and comp_h > comp_w * 0.28:
                letters += 1
                area += comp_area
        flags.append(letters >= 3 and area >= min_total)
    return flags


def _sample_pen(image: np.ndarray, lines: list[float], occupied: list[bool], pitch: float) -> tuple[int, int, int] | None:
    if not any(occupied):
        return None
    mask = _pen_ink(image, pitch if pitch > 0 else 0.04)
    height, width = mask.shape
    chosen = np.zeros(mask.shape, np.uint8)
    step = pitch if pitch > 0 else 0.04
    for index, (y, taken) in enumerate(zip(lines, occupied)):
        if not taken:
            continue
        above = lines[index - 1] if index else y - step
        y0 = int(round(above * height)) + 2
        y1 = int(round(y * height)) - 1
        chosen[max(0, y0) : min(height, y1), int(width * 0.16) : int(width * 0.94)] = 1
    selected = (mask > 0) & (chosen > 0)
    if int(selected.sum()) < 40:
        return None
    bgr = np.percentile(image[selected], 30, axis=0)
    rgb = (int(np.clip(bgr[2], 0, 255)), int(np.clip(bgr[1], 0, 255)), int(np.clip(bgr[0], 0, 255)))
    if sum(rgb) / 3 > 170:
        return None
    return rgb


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
    periodic, periodic_pitch = _periodic_rules(warped)
    detected = _rules(warped)
    if periodic and periodic_pitch and len(periodic) >= 6:
        lines = periodic
        pitch = periodic_pitch
        found_rules = True
    elif len(detected) >= 4:
        found_rules = True
        pitch = _estimate_pitch(detected) or float(np.median(np.diff(detected)))
        lines = _grid(detected, pitch)
    else:
        lines = _even_lines()
        pitch = lines[1] - lines[0]
        found_rules = False
    occupied = _mark_occupied(warped, lines, pitch or 0.04)
    pen = _sample_pen(warped, lines, occupied, pitch or 0.04)
    # Writing sits on the line, so the detected rule is the baseline.
    return PreparedPage(
        image=warped,
        lines=lines,
        found_page=found or found_rules,
        occupied=occupied,
        pitch=float(pitch or 0.0),
        pen_rgb=pen,
    )
