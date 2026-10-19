"""Notebook page backgrounds.

Geometry is in millimetres so a page is A4 at any DPI.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw

from qalam.renderer.paint import dotted_hline, hline

PAPER = (255, 252, 246, 255)
RULE = (176, 198, 230, 255)
RULE_STRONG = (126, 162, 214, 255)
MARGIN = (214, 96, 90, 255)
GRID = (186, 204, 228, 255)
GRID_GUIDE = (214, 224, 238, 255)
HOLE = (196, 186, 170, 255)
EDGE = (232, 222, 206, 255)


def mm(dpi: int, value: float) -> int:
    return int(round(value / 25.4 * dpi))


def a4_px(dpi: int) -> tuple[int, int]:
    return mm(dpi, 210), mm(dpi, 297)


@dataclass
class PageGeometry:
    image: Image.Image
    kind: str
    left: int
    right: int
    top: int
    bottom: int
    line_height: int
    baseline_offset: int
    cell: int = 0
    cols: int = 0
    rows: int = 0
    grid_left: int = 0
    grid_top: int = 0

    @property
    def width(self) -> int:
        return self.right - self.left

    def baselines(self) -> list[int]:
        slots = []
        y = self.top
        while y + self.line_height <= self.bottom + 1:
            slots.append(y + self.baseline_offset)
            y += self.line_height
        return slots


def _stroke(dpi: int) -> int:
    return max(1, round(dpi / 96))


def _holes(draw: ImageDraw.ImageDraw, dpi: int, x: int, top: int, bottom: int) -> None:
    radius = mm(dpi, 3.2)
    for frac in (0.22, 0.5, 0.78):
        cy = int(top + (bottom - top) * frac)
        draw.ellipse(
            (x - radius, cy - radius, x + radius, cy + radius),
            outline=HOLE,
            width=_stroke(dpi),
        )


def _base(dpi: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    width, height = a4_px(dpi)
    image = Image.new("RGBA", (width, height), PAPER)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, height - 1), outline=EDGE)
    return image, draw


def make_page(
    template_id: str,
    dpi: int,
    direction: str,
    line_mm: float,
) -> PageGeometry:
    image, draw = _base(dpi)
    width, height = image.size
    stroke = _stroke(dpi)
    header_top = mm(dpi, 12)
    header_bottom = mm(dpi, 24)
    footer = height - mm(dpi, 12)

    if template_id in {"tianzige", "square-grid"}:
        return _grid(image, draw, dpi, template_id, header_bottom, footer, stroke)

    outer = mm(dpi, 14)
    red = mm(dpi, 28)
    if direction == "rtl":
        left = outer
        right = width - red - mm(dpi, 4)
        red_x = width - red
        hole_x = width - mm(dpi, 12)
    else:
        left = red + mm(dpi, 4)
        right = width - outer
        red_x = red
        hole_x = mm(dpi, 12)

    draw.line((red_x, header_bottom, red_x, footer), fill=MARGIN, width=stroke + 1)
    _holes(draw, dpi, hole_x, header_top, footer)

    if template_id == "four-line":
        band = mm(dpi, 18)
        gap = mm(dpi, 3.5)
        pitch = band + gap
        y = header_bottom + mm(dpi, 2)
        while y + band <= footer:
            top = y
            mid = y + band // 3
            base = y + (2 * band) // 3
            bot = y + band
            hline(draw, left, right, top, RULE, stroke)
            dotted_hline(draw, left, right, mid, RULE, stroke, max(7, mm(dpi, 1.8)))
            hline(draw, left, right, base, RULE_STRONG, stroke)
            hline(draw, left, right, bot, RULE, stroke)
            y += pitch
        return PageGeometry(
            image=image,
            kind="flow",
            left=left,
            right=right,
            top=header_bottom + mm(dpi, 2),
            bottom=footer,
            line_height=pitch,
            baseline_offset=(2 * band) // 3,
        )

    line_h = max(mm(dpi, 8), mm(dpi, line_mm))
    y = header_bottom + line_h
    while y <= footer:
        hline(draw, left, right, y, RULE, stroke)
        y += line_h
    return PageGeometry(
        image=image,
        kind="flow",
        left=left,
        right=right,
        top=header_bottom,
        bottom=footer,
        line_height=line_h,
        baseline_offset=line_h,
    )


def _grid(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    dpi: int,
    template_id: str,
    header_bottom: int,
    footer: int,
    stroke: int,
) -> PageGeometry:
    width, _height = image.size
    margin = mm(dpi, 14)
    cols = 8 if template_id == "tianzige" else 10
    content_w = width - margin * 2
    cell = content_w // cols
    grid_w = cell * cols
    grid_left = margin + (content_w - grid_w) // 2
    rows = max(1, (footer - header_bottom - mm(dpi, 2)) // cell)
    grid_h = rows * cell
    grid_top = header_bottom + mm(dpi, 2) + ((footer - header_bottom - mm(dpi, 2)) - grid_h) // 2
    for row in range(rows):
        for col in range(cols):
            x = grid_left + col * cell
            y = grid_top + row * cell
            draw.rectangle((x, y, x + cell, y + cell), outline=GRID, width=stroke)
            if template_id == "tianzige":
                mid_x = x + cell // 2
                mid_y = y + cell // 2
                dotted_hline(draw, x + 2, x + cell - 2, mid_y, GRID_GUIDE, stroke, max(6, cell // 8))
                step = max(6, cell // 8)
                dash = max(2, step // 2)
                yy = y + 2
                while yy < y + cell - 2:
                    draw.line((mid_x, yy, mid_x, min(yy + dash, y + cell - 2)), fill=GRID_GUIDE, width=stroke)
                    yy += step
    return PageGeometry(
        image=image,
        kind="grid",
        left=grid_left,
        right=grid_left + grid_w,
        top=grid_top,
        bottom=grid_top + grid_h,
        line_height=cell,
        baseline_offset=int(cell * 0.78),
        cell=cell,
        cols=cols,
        rows=rows,
        grid_left=grid_left,
        grid_top=grid_top,
    )
