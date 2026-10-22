"""Lay Graves strokes onto a notebook page.

Latin text is synthesised. The page, the header, and every other script
stay with the font renderer.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
from PIL import Image, ImageDraw

from qalam.models import RenderRequest, RenderResult
from qalam.registry import ink_by_id
from qalam.renderer.engine import FontHandwritingRenderer
from qalam.renderer.markup import parse_line, split_lines
from qalam.renderer.paint import draw_text, measure_width
from qalam.renderer.stroke import _INDEX, cached_line, model_available, polylines
from qalam.renderer.templates import make_page, mm


def render_stroke_page(fonts: FontHandwritingRenderer, request: RenderRequest) -> RenderResult:
    if not model_available():
        ink = request.ink_id if request.ink_id != "sample" else "blue"
        return fonts.render(replace(request, ink_id=ink))
    with fonts.library.lock:
        return _locked(fonts, request)


def _locked(fonts: FontHandwritingRenderer, request: RenderRequest) -> RenderResult:
    language = fonts.registry.language(request.language_id)
    ink_id = request.ink_id if request.ink_id != "sample" else "navy"
    ink = ink_by_id(ink_id)
    font_cfg = fonts.registry.font(language.font)
    px = fonts._font_px(request.template_id, font_cfg.line_mm, font_cfg.body_ratio, request.dpi, request.page_size)
    page = make_page(
        request.template_id if request.template_id not in {"tianzige", "genko", "wongoji"} else "single-ruled",
        request.dpi,
        language.direction,
        font_cfg.line_mm,
        request.page_size,
        request.margin,
    )
    fonts._draw_header(page, request, language, px, ink)
    lines = _marked(request.text)
    slots = page.baselines()
    slot = 0
    pages: list[Image.Image] = []
    number = 1
    bias = int(round((0.82 - 0.5 * min(1.0, max(0.0, request.variation))) * 1000))
    trace = request.trace
    thickness = request.thickness

    def fresh():
        nonlocal page, slots, slot, number
        fonts._stamp_page_number(page, number, request.dpi)
        pages.append(page.image.convert("RGB"))
        number += 1
        page = make_page(
            request.template_id if request.template_id not in {"tianzige", "genko", "wongoji"} else "single-ruled",
            request.dpi,
            language.direction,
            font_cfg.line_mm,
            request.page_size,
            request.margin,
        )
        fonts._draw_header(page, request, language, px, ink)
        slots = page.baselines()
        slot = 0

    for index, line in enumerate(lines):
        if slot >= len(slots):
            if len(pages) + 1 >= request.max_pages:
                break
            fresh()
        if line["rule"]:
            y = slots[slot] - max(2, page.line_height // 5)
            ImageDraw.Draw(page.image).line(
                (page.left, y, page.right, y),
                fill=(*ink["rgb"], 200),
                width=max(1, int(round(thickness))),
            )
        elif line["text"]:
            height = page.line_height * (1.2 if line["scale"] > 1 else 0.78)
            drawn = _draw_mixed(
                fonts,
                page.image,
                line["text"],
                page.left,
                page.right,
                slots[slot],
                height,
                ink["rgb"],
                request.dpi,
                thickness,
                trace,
                request.seed + index * 17,
                bias,
                px,
            )
            if line["underline"] and drawn > 4:
                y = int(slots[slot] + max(2, page.line_height * 0.08))
                ImageDraw.Draw(page.image).line(
                    (page.left, y, page.left + drawn, y),
                    fill=(*ink["rgb"], 210),
                    width=max(1, int(round(thickness))),
                )
        slot += 1
    fonts._stamp_page_number(page, number, request.dpi)
    pages.append(page.image.convert("RGB"))
    return RenderResult(
        pages=pages or [page.image.convert("RGB")],
        truncated=False,
        width=pages[0].width if pages else 0,
        height=pages[0].height if pages else 0,
    )


def _marked(text: str, limit: int = 32) -> list[dict]:
    lines: list[dict] = []
    for raw in split_lines(text.replace("\r\n", "\n").replace("\r", "\n")):
        runs = parse_line(raw)
        if not runs:
            lines.append({"text": "", "rule": False, "underline": False, "scale": 1.0})
            continue
        if len(runs) == 1 and runs[0].rule:
            lines.append({"text": "", "rule": True, "underline": False, "scale": 1.0})
            continue
        chunks: list[tuple[str, bool, float]] = []
        for run in runs:
            body = ("- " if run.bullet else "") + run.text
            chunks.append((body, run.underline, run.scale))
        words: list[tuple[str, bool, float]] = []
        for body, underline, scale in chunks:
            parts = body.split(" ")
            for index, word in enumerate(parts):
                if index:
                    words.append((" ", underline, scale))
                if word:
                    words.append((word, underline, scale))
        current = ""
        current_under = False
        current_scale = 1.0
        for word, underline, scale in words:
            trial = f"{current}{word}"
            if len(trial) > limit and current.strip():
                lines.append({"text": current.strip(), "rule": False, "underline": current_under, "scale": current_scale})
                current = word.strip()
                current_under = underline
                current_scale = scale
            else:
                current = trial
                current_under = current_under or underline
                current_scale = max(current_scale, scale)
        if current.strip():
            lines.append({"text": current.strip(), "rule": False, "underline": current_under, "scale": current_scale})
    return lines or [{"text": "", "rule": False, "underline": False, "scale": 1.0}]


def _segments(text: str) -> list[tuple[bool, str]]:
    groups: list[tuple[bool, str]] = []
    buffer = ""
    mode: bool | None = None
    for char in text:
        stroke = char in _INDEX and char != "\x00"
        if mode is None:
            mode = stroke
        if stroke != mode:
            groups.append((mode, buffer))
            buffer = char
            mode = stroke
        else:
            buffer += char
    if buffer and mode is not None:
        groups.append((mode, buffer))
    return groups


def _draw_mixed(fonts, image, text, left, right, baseline, target_h, rgb, dpi, thickness, trace, seed, bias, px) -> float:
    cursor = float(left)
    limit = float(right)
    for index, (stroke, chunk) in enumerate(_segments(text)):
        if cursor >= limit - 4:
            break
        if stroke:
            offsets = np.array(cached_line(chunk, seed + index * 3, bias), dtype=np.float32)
            width = _draw_line(image, offsets, cursor, limit, baseline, target_h, rgb, dpi, thickness, trace)
        else:
            width = _draw_font(fonts, image, chunk, cursor, baseline, px, rgb)
        cursor += max(width, 0)
    return cursor - left


def _draw_font(fonts, image, text, x, baseline, px, rgb) -> float:
    language = fonts.registry.language("en")
    font_id = fonts.pick_font(text, language)
    glyphs = fonts.library.shape(font_id, text, px * 0.9)
    width = measure_width(glyphs)
    draw_text(image, glyphs, x, baseline, px * 0.9, fonts.library, rgb, 0.95)
    return width


def _draw_line(image, offsets, left, right, baseline, target_h, rgb, dpi, thickness, trace) -> float:
    parts = polylines(offsets.reshape(-1, 3) if len(offsets) else offsets)
    if not parts:
        return 0.0
    pts = np.vstack(parts)
    if len(pts) >= 4:
        slope = np.polyfit(pts[:, 0], pts[:, 1], 1)[0]
        theta = np.arctan(slope)
        rot = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]], np.float32)
        parts = [part @ rot for part in parts]
        pts = np.vstack(parts)
    width = float(pts[:, 0].max() - pts[:, 0].min())
    height = float(pts[:, 1].max() - pts[:, 1].min())
    room = max(8.0, right - left)
    scale = max(8.0, target_h) / max(height, 1e-3)
    if width * scale > room:
        scale = room / max(width, 1e-3)
    origin = pts.min(axis=0)
    body = float(np.percentile(pts[:, 1], 70))
    pen = max(1, int(round(dpi / 90 * max(0.6, min(thickness, 2.2)))))
    color = (*rgb, 90 if trace else 230)
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for part in parts:
        placed = (part - np.array([origin[0], body])) * scale
        placed[:, 0] += left
        placed[:, 1] += baseline
        seq = [(float(point[0]), float(point[1])) for point in placed]
        if trace:
            _dashed(draw, seq, color, pen)
        elif len(seq) >= 2:
            draw.line(seq, fill=color, width=pen, joint="curve")
    image.alpha_composite(overlay)
    return float(width * scale)


def _dashed(draw: ImageDraw.ImageDraw, seq: list[tuple], color, width: int) -> None:
    draw_on = True
    acc = 0.0
    step = 5.0
    for start, end in zip(seq, seq[1:]):
        dist = ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5
        if draw_on and dist > 0.4:
            draw.line((start, end), fill=color, width=width)
        acc += dist
        if acc >= step:
            draw_on = not draw_on
            acc = 0.0
