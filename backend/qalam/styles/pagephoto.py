"""Straighten a photo of a notebook page and find the lines it was ruled with.

The page becomes the background. Handwriting is drawn on the detected
rules and multiplied into the photo, so the paper texture stays.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from qalam.styles.extract import read_image


@dataclass
class PreparedPage:
    image: np.ndarray  # BGR, straightened
    lines: list[float]  # baseline y, 0..1 of the image height
    found_page: bool

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


def prepare_page(data: bytes) -> PreparedPage:
    image = read_image(data)
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
    lines = _rules(warped)
    if len(lines) < 4:
        lines = _even_lines()
        found_rules = False
    else:
        found_rules = True
    # Writing sits on the line, so the detected rule is the baseline.
    return PreparedPage(image=warped, lines=lines, found_page=found or found_rules)
