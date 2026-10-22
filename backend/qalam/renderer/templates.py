"""Notebook page backgrounds.

Geometry is in millimetres so a page stays the right shape at any DPI.
A4 is the school default. Letter is the other size. The red margin can
sit narrow, standard, or wide.
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
GRAPH = (214, 226, 240, 255)
HOLE = (196, 186, 170, 255)
EDGE = (232, 222, 206, 255)

PAGE_MM = {
    "a4": (210.0, 297.0),
    "letter": (215.9, 279.4),
}
MARGIN_MM = {
    "narrow": 18.0,
    "standard": 28.0,
    "wide": 40.0,
}


def mm(dpi: int, value: float) -> int:
    return int(round(value / 25.4 * dpi))


def page_px(dpi: int, page_size: str = "a4") -> tuple[int, int]:
    width, height = PAGE_MM.get(page_size, PAGE_MM["a4"])
    return mm(dpi, width), mm(dpi, height)


def a4_px(dpi: int) -> tuple[int, int]:
    return page_px(dpi, "a4")


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
    gutter: int = 0
    gutter_at: int = -1

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

    def cell_origin(self, row: int, col: int) -> tuple[int, int]:
        shift = self.gutter if self.gutter_at >= 0 and col > self.gutter_at else 0
        return self.grid_left + col * self.cell + shift, self.grid_top + row * self.cell


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


def _base(dpi: int, page_size: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    width, height = page_px(dpi, page_size)
    image = Image.new("RGBA", (width, height), PAPER)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, height - 1), outline=EDGE)
    return image, draw


def make_page(
    template_id: str,
    dpi: int,
    direction: str,
    line_mm: float,
    page_size: str = "a4",
    margin: str = "standard",
) -> PageGeometry:
    image, draw = _base(dpi, page_size)
    width, height = image.size
    stroke = _stroke(dpi)
    header_top = mm(dpi, 12)
    header_bottom = mm(dpi, 46) if template_id == "worksheet" else mm(dpi, 24)
    footer = height - mm(dpi, 12)
    red_mm = MARGIN_MM.get(margin, MARGIN_MM["standard"])

    if template_id in {"tianzige", "square-grid", "genko", "wongoji"}:
        return _grid(image, draw, dpi, template_id, header_bottom, footer, stroke)

    if template_id == "graph":
        return _graph(image, draw, dpi, header_bottom, footer, stroke, red_mm, direction)

    outer = mm(dpi, 14)
    red = mm(dpi, red_mm)
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
        return _bands(image, draw, dpi, left, right, header_bottom, footer, stroke, guides=4)
    if template_id == "urdu-copy":
        return _bands(image, draw, dpi, left, right, header_bottom, footer, stroke, guides=3)

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


def _bands(image, draw, dpi, left, right, header_bottom, footer, stroke, guides: int) -> PageGeometry:
    band = mm(dpi, 16 if guides == 3 else 18)
    gap = mm(dpi, 3.5)
    pitch = band + gap
    y = header_bottom + mm(dpi, 2)
    while y + band <= footer:
        top = y
        mid = y + band // 2 if guides == 3 else y + band // 3
        base = y + (2 * band) // 3
        bot = y + band
        hline(draw, left, right, top, RULE, stroke)
        dotted_hline(draw, left, right, mid, RULE, stroke, max(7, mm(dpi, 1.8)))
        hline(draw, left, right, base, RULE_STRONG, stroke)
        if guides == 4:
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


def _graph(image, draw, dpi, header_bottom, footer, stroke, red_mm, direction) -> PageGeometry:
    width, _height = image.size
    cell = max(mm(dpi, 6.5), 8)
    outer = mm(dpi, 12)
    red = mm(dpi, red_mm)
    if direction == "rtl":
        left = outer
        right = width - red
        red_x = width - red
    else:
        left = red
        right = width - outer
        red_x = red
    draw.line((red_x, header_bottom, red_x, footer), fill=MARGIN, width=stroke + 1)
    span_w = right - left
    span_h = footer - header_bottom
    cols = max(1, span_w // cell)
    rows = max(1, span_h // cell)
    grid_w = cols * cell
    grid_h = rows * cell
    grid_left = left + (span_w - grid_w) // 2
    grid_top = header_bottom + (span_h - grid_h) // 2
    for col in range(cols + 1):
        x = grid_left + col * cell
        draw.line((x, grid_top, x, grid_top + grid_h), fill=GRAPH, width=stroke)
    for row in range(rows + 1):
        y = grid_top + row * cell
        hline(draw, grid_left, grid_left + grid_w, y, GRAPH, stroke)
    return PageGeometry(
        image=image,
        kind="flow",
        left=grid_left + mm(dpi, 2),
        right=grid_left + grid_w - mm(dpi, 2),
        top=grid_top,
        bottom=grid_top + grid_h,
        line_height=cell,
        baseline_offset=cell - max(1, cell // 8),
    )


def _grid(image, draw, dpi, template_id, header_bottom, footer, stroke) -> PageGeometry:
    width, _height = image.size
    margin = mm(dpi, 14)
    if template_id == "genko":
        cols = 20
        gutter_at = 9
        gutter = mm(dpi, 6)
    elif template_id == "tianzige":
        cols = 8
        gutter_at = -1
        gutter = 0
    else:
        cols = 10
        gutter_at = -1
        gutter = 0
    content_w = width - margin * 2
    cell = max(8, (content_w - gutter) // cols)
    grid_w = cell * cols + gutter
    grid_left = margin + (content_w - grid_w) // 2
    rows = max(1, (footer - header_bottom - mm(dpi, 2)) // cell)
    grid_h = rows * cell
    grid_top = header_bottom + mm(dpi, 2) + ((footer - header_bottom - mm(dpi, 2)) - grid_h) // 2
    if template_id == "wongoji":
        draw.line(
            (grid_left - mm(dpi, 3), grid_top, grid_left - mm(dpi, 3), grid_top + grid_h),
            fill=MARGIN,
            width=stroke + 1,
        )
    for row in range(rows):
        for col in range(cols):
            shift = gutter if gutter_at >= 0 and col > gutter_at else 0
            x = grid_left + col * cell + shift
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
        gutter=gutter,
        gutter_at=gutter_at,
    )
