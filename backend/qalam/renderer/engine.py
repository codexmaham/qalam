"""Font-based handwriting engine.

Pipeline for a page of notes:

1. Segment the text into words or grapheme clusters.
2. Pick a font per unit (the language font, or a fallback that covers it).
3. Shape with HarfBuzz so Arabic, Indic, and Thai marks land correctly.
4. Nudge glyphs with a deterministic jitter profile that respects joining.
5. Flow the units onto a notebook template and rasterise with FreeType.

`FontHandwritingRenderer.render` is the method a stroke engine would replace.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field

import regex
from PIL import Image, ImageDraw

from qalam.models import RenderRequest, RenderResult
from qalam.registry import Language, Registry, ink_by_id, load_registry, template_by_id
from qalam.renderer.fonts import FontLibrary
from qalam.renderer.jitter import ShapedGlyph, apply_jitter, rng_for
from qalam.renderer.paint import draw_glyphs, draw_text, measure_width
from qalam.renderer.markup import parse_line, split_lines
from qalam.renderer.segment import CLUSTER_SCRIPTS, dominant_script, segment
from qalam.renderer.templates import PageGeometry, make_page, mm, page_px

MAX_CHARS = 12000
LABEL = (120, 132, 156)


@dataclass
class Unit:
    text: str
    font_id: str
    script: str
    glyphs: list[ShapedGlyph] = field(default_factory=list)
    width: float = 0
    is_space: bool = False
    is_break: bool = False
    underline: bool = False
    rule: bool = False


class FontHandwritingRenderer:
    def __init__(self, registry: Registry | None = None) -> None:
        self.registry = registry or load_registry()
        self.library = FontLibrary(self.registry)
        self._page_cache: dict[str, tuple[list[bytes], bool]] = {}

    def render(self, request: RenderRequest) -> RenderResult:
        language = self.registry.language(request.language_id)
        template_by_id(request.template_id)
        ink = ink_by_id(request.ink_id)
        text = request.text.replace("\r\n", "\n").replace("\r", "\n")
        truncated = False
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS]
            truncated = True
        key = self._cache_key(request, text)
        with self.library.lock:
            cached = self._page_cache.get(key)
            if cached is not None:
                blobs, overflow = cached
                pages = [Image.open(io.BytesIO(blob)).convert("RGB") for blob in blobs]
                return RenderResult(
                    pages=pages,
                    truncated=truncated or overflow,
                    width=pages[0].width if pages else 0,
                    height=pages[0].height if pages else 0,
                )
            pages = self._render_locked(request, language, text, ink)
            blobs = []
            rgb_pages = []
            for page in pages:
                rgb = page.convert("RGB")
                rgb_pages.append(rgb)
                buf = io.BytesIO()
                rgb.save(buf, format="PNG", optimize=True)
                blobs.append(buf.getvalue())
            if len(self._page_cache) > 24:
                self._page_cache.clear()
            overflow = self._overflowed
            self._page_cache[key] = (blobs, overflow)
            return RenderResult(
                pages=rgb_pages,
                truncated=truncated or overflow,
                width=rgb_pages[0].width if rgb_pages else 0,
                height=rgb_pages[0].height if rgb_pages else 0,
            )

    def render_pdf(self, request: RenderRequest) -> tuple[bytes, bool]:
        result = self.render(request)
        if not result.pages:
            raise RuntimeError("Renderer produced no pages")
        buffer = io.BytesIO()
        result.pages[0].save(
            buffer,
            format="PDF",
            save_all=True,
            append_images=result.pages[1:],
            resolution=float(request.dpi),
        )
        return buffer.getvalue(), result.truncated

    def _cache_key(self, request: RenderRequest, text: str) -> str:
        payload = "|".join(
            [
                text,
                request.language_id,
                request.template_id,
                request.ink_id,
                request.name,
                request.date,
                request.class_name,
                request.page_size,
                request.margin,
                f"{request.thickness:.2f}",
                "trace" if request.trace else "",
                str(request.dpi),
                str(request.max_pages),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _render_locked(self, request: RenderRequest, language: Language, text: str, ink: dict) -> list[Image.Image]:
        self._overflowed = False
        font_cfg = self.registry.font(language.font)
        px = self._font_px(request.template_id, font_cfg.line_mm, font_cfg.body_ratio, request.dpi, request.page_size)
        units = self._shape_units(text, language, px)
        page = make_page(
            request.template_id,
            request.dpi,
            language.direction,
            font_cfg.line_mm,
            request.page_size,
            request.margin,
        )
        self._draw_header(page, request, language, px, ink)
        if page.kind == "grid":
            images = self._layout_grid(page, units, request, language, px, ink)
        else:
            images = self._layout_flow(page, units, request, language, px, ink, font_cfg.line_mm)
        return images

    def _font_px(self, template_id: str, line_mm: float, body_ratio: float, dpi: int, page_size: str = "a4") -> float:
        if template_id == "four-line":
            return mm(dpi, 18) * 0.50
        if template_id == "urdu-copy":
            return mm(dpi, 16) * 0.55
        if template_id == "graph":
            return mm(dpi, 6.5) * 0.62
        if template_id == "tianzige":
            return self._cell(dpi, 8, page_size) * 0.66
        if template_id in {"square-grid", "wongoji"}:
            return self._cell(dpi, 10, page_size) * 0.66
        if template_id == "genko":
            return self._cell(dpi, 20, page_size) * 0.62
        return max(8.0, mm(dpi, line_mm) * body_ratio)

    def _cell(self, dpi: int, cols: int, page_size: str = "a4") -> int:
        width, _height = page_px(dpi, page_size)
        content = width - mm(dpi, 14) * 2
        return max(8, content // cols)

    def pick_font(self, text: str, language: Language) -> str:
        script = dominant_script(text)
        primary = self.registry.font(language.font)
        if script in {"Zyyy", "Zinh"} or script in primary.scripts:
            if self.library.covers(language.font, text):
                return language.font
        if script not in {"Zyyy", "Zinh"}:
            for font_id, config in self.registry.fonts.items():
                if script in config.scripts and self.library.covers(font_id, text):
                    return font_id
        for font_id in language.fallbacks:
            if self.library.covers(font_id, text):
                return font_id
        if self.library.covers(language.font, text):
            return language.font
        for font_id in self.registry.fonts:
            if self.library.covers(font_id, text):
                return font_id
        return language.font

    def _shape_units(self, text: str, language: Language, px: float) -> list[Unit]:
        shaped: list[Unit] = []
        index = 0
        for raw_line in split_lines(text):
            runs = parse_line(raw_line)
            if not runs:
                shaped.append(Unit(text="\n", font_id=language.font, script="Zyyy", is_break=True))
                continue
            if len(runs) == 1 and runs[0].rule:
                shaped.append(Unit(text="", font_id=language.font, script="Zyyy", rule=True))
                shaped.append(Unit(text="\n", font_id=language.font, script="Zyyy", is_break=True))
                continue
            for run in runs:
                body = f"• {run.text}" if run.bullet else run.text
                size = px * run.scale
                for raw in segment(body):
                    font_id = self.pick_font(raw, language)
                    config = self.registry.font(font_id)
                    glyphs = self.library.shape(font_id, raw, size)
                    apply_jitter(
                        glyphs,
                        config.jitter,
                        config.jitter_amount,
                        size,
                        rng_for(language.id, font_id, str(index), raw),
                    )
                    shaped.append(
                        Unit(
                            text=raw,
                            font_id=font_id,
                            script=dominant_script(raw),
                            glyphs=glyphs,
                            width=measure_width(glyphs),
                            is_space=raw.strip() == "",
                            underline=run.underline,
                        )
                    )
                    index += 1
            shaped.append(Unit(text="\n", font_id=language.font, script="Zyyy", is_break=True))
        if shaped and shaped[-1].is_break:
            shaped.pop()
        return shaped

    def _shape_plain(self, text: str, font_id: str, px: float) -> list[ShapedGlyph]:
        return self.library.shape(font_id, text, px)

    def _draw_header(
        self,
        page: PageGeometry,
        request: RenderRequest,
        language: Language,
        px: float,
        ink: dict,
    ) -> None:
        draw = ImageDraw.Draw(page.image)
        label_px = max(12, px * 0.55)
        baseline = mm(request.dpi, 18)
        left = mm(request.dpi, 14)
        right = page.image.width - mm(request.dpi, 14)
        rgb = ink["rgb"]
        if request.template_id == "worksheet":
            self._draw_worksheet_header(page, request, language, px, ink)
            return
        name = request.name.strip()
        date = request.date.strip()
        if request.class_name.strip():
            name = f"{name}  ·  {request.class_name.strip()}".strip(" ·")
        if language.direction == "rtl":
            self._header_pair(page, "Date", date, left, baseline, label_px, px, language, rgb, align="left")
            self._header_pair(page, "Name", name, right, baseline, label_px, px, language, rgb, align="right")
        else:
            self._header_pair(page, "Name", name, left, baseline, label_px, px, language, rgb, align="left")
            self._header_pair(page, "Date", date, right, baseline, label_px, px, language, rgb, align="right")
        # A quiet rule under the header so the sheet has a top edge.
        draw.line(
            (left, mm(request.dpi, 22), right, mm(request.dpi, 22)),
            fill=(226, 214, 196, 255),
            width=max(1, request.dpi // 120),
        )

    def _draw_worksheet_header(self, page, request, language, px, ink) -> None:
        draw = ImageDraw.Draw(page.image)
        width = page.image.width
        fields = (
            ("Name", request.name.strip()),
            ("Date", request.date.strip()),
            ("Class", request.class_name.strip()),
        )
        gap = mm(request.dpi, 6)
        span = (width - mm(request.dpi, 28) - gap * 2) // 3
        label_px = max(12, px * 0.5)
        y = mm(request.dpi, 20)
        x = mm(request.dpi, 14)
        rgb = ink["rgb"]
        for label, value in fields:
            self._header_pair(page, label, value, x, y, label_px, px, language, rgb, align="left")
            if not value:
                rule_y = y + int(label_px * 0.2)
                draw.line((x + int(label_px * 2.6), rule_y, x + span - 8, rule_y), fill=(196, 176, 160, 255), width=1)
            x += span + gap

    def _header_pair(
        self,
        page: PageGeometry,
        label: str,
        value: str,
        anchor: int,
        baseline: int,
        label_px: float,
        value_px: float,
        language: Language,
        rgb: tuple[int, int, int],
        align: str,
    ) -> None:
        label_glyphs = self._shape_plain(label, "caveat", label_px)
        label_w = measure_width(label_glyphs)
        value_font = self.pick_font(value, language) if value else language.font
        value_glyphs = self._shape_plain(value, value_font, value_px * 0.72) if value else []
        value_w = measure_width(value_glyphs)
        gap = label_px * 0.4
        rule = max(value_px * 2.4, label_px * 4)
        if align == "left":
            x = anchor
            draw_text(page.image, label_glyphs, x, baseline, label_px, self.library, LABEL, 1)
            x += label_w + gap
            if value_glyphs:
                draw_text(page.image, value_glyphs, x, baseline, value_px * 0.72, self.library, rgb, 1)
            else:
                y = int(baseline + label_px * 0.15)
                ImageDraw.Draw(page.image).line((x, y, x + rule, y), fill=(196, 176, 160, 255), width=1)
        else:
            total = label_w + gap + (value_w if value_glyphs else rule)
            x = anchor - total
            draw_text(page.image, label_glyphs, x, baseline, label_px, self.library, LABEL, 1)
            x += label_w + gap
            if value_glyphs:
                draw_text(page.image, value_glyphs, x, baseline, value_px * 0.72, self.library, rgb, 1)
            else:
                y = int(baseline + label_px * 0.15)
                ImageDraw.Draw(page.image).line((x, y, x + rule, y), fill=(196, 176, 160, 255), width=1)

    def _fresh_page(self, request: RenderRequest, language: Language, ink: dict, px: float, line_mm: float) -> PageGeometry:
        page = make_page(
            request.template_id,
            request.dpi,
            language.direction,
            line_mm,
            request.page_size,
            request.margin,
        )
        self._draw_header(page, request, language, px, ink)
        return page

    def _stamp_page_number(self, page: PageGeometry, number: int, dpi: int) -> None:
        glyphs = self._shape_plain(str(number), "caveat", max(11, dpi * 0.11))
        width = measure_width(glyphs)
        x = (page.image.width - width) / 2
        baseline = page.image.height - mm(dpi, 7)
        draw_text(page.image, glyphs, x, baseline, max(11, dpi * 0.11), self.library, LABEL, 1)

    def _layout_flow(
        self,
        first: PageGeometry,
        units: list[Unit],
        request: RenderRequest,
        language: Language,
        px: float,
        ink: dict,
        line_mm: float,
    ) -> list[Image.Image]:
        paragraphs = self._paragraphs(units)
        pages: list[Image.Image] = []
        page = first
        slots = page.baselines()
        slot = 0
        rgb = ink["rgb"]
        alpha = ink["alpha"]

        def new_page() -> None:
            nonlocal page, slots, slot
            self._stamp_page_number(page, len(pages) + 1, request.dpi)
            pages.append(page.image)
            page = self._fresh_page(request, language, ink, px, line_mm)
            slots = page.baselines()
            slot = 0

        for paragraph in paragraphs:
            if not paragraph:
                slot += 1
                if slot >= len(slots):
                    if len(pages) + 1 >= request.max_pages:
                        self._overflowed = True
                        self._stamp_page_number(page, len(pages) + 1, request.dpi)
                        pages.append(page.image)
                        return pages
                    new_page()
                continue
            total = sum(unit.width for unit in paragraph if not unit.is_space)
            indent = px * 1.15 if total > page.width else 0
            first_line = True
            rest = paragraph
            while rest:
                if slot >= len(slots):
                    if len(pages) + 1 >= request.max_pages:
                        self._overflowed = True
                        self._stamp_page_number(page, len(pages) + 1, request.dpi)
                        pages.append(page.image)
                        return pages
                    new_page()
                    first_line = False
                budget = page.width - (indent if first_line else 0)
                line, rest = self._take_line(rest, budget, px)
                if not line:
                    break
                if len(line) == 1 and line[0].rule:
                    rule_y = slots[slot] - px * 0.2
                    ImageDraw.Draw(page.image).line(
                        (page.left, rule_y, page.right, rule_y),
                        fill=(*rgb, 180),
                        width=max(1, int(round(request.thickness))),
                    )
                else:
                    self._draw_line(
                        page,
                        line,
                        slots[slot],
                        language.direction,
                        indent if first_line else 0,
                        px,
                        rgb,
                        alpha,
                        request.trace,
                        request.thickness,
                    )
                slot += 1
                first_line = False
        self._stamp_page_number(page, len(pages) + 1, request.dpi)
        pages.append(page.image)
        return pages or [first.image]

    def _paragraphs(self, units: list[Unit]) -> list[list[Unit] | None]:
        paragraphs: list[list[Unit] | None] = []
        current: list[Unit] = []
        for unit in units:
            if unit.is_break:
                paragraphs.append(current)
                current = []
            else:
                current.append(unit)
        paragraphs.append(current)
        # A trailing break should not invent a blank page. Drop a final empty
        # paragraph that came from a terminating newline, but keep interior blanks.
        if paragraphs and paragraphs[-1] == [] and len(paragraphs) > 1:
            paragraphs.pop()
        return paragraphs

    def _take_line(self, units: list[Unit], budget: float, px: float) -> tuple[list[Unit], list[Unit]]:
        if units and not units[0].is_space and units[0].width > budget and units[0].script not in {"Arab"} and len(units[0].text) > 1:
            units = self._explode(units[0], px) + units[1:]
        line: list[Unit] = []
        width = 0.0
        index = 0
        while index < len(units):
            unit = units[index]
            if unit.is_space and not line:
                index += 1
                continue
            if line and width + unit.width > budget:
                break
            line.append(unit)
            width += unit.width
            index += 1
            if width > budget:
                break
        return line, units[index:]

    def _reshape(self, text: str, font_id: str, px: float) -> Unit:
        glyphs = self.library.shape(font_id, text, px)
        return Unit(
            text=text,
            font_id=font_id,
            script=dominant_script(text),
            glyphs=glyphs,
            width=measure_width(glyphs),
        )

    def _explode(self, unit: Unit, px: float) -> list[Unit]:
        return [self._reshape(cluster, unit.font_id, px) for cluster in regex.findall(r"\X", unit.text)]

    def _draw_line(
        self,
        page: PageGeometry,
        line: list[Unit],
        baseline: int,
        direction: str,
        indent: float,
        px: float,
        rgb: tuple[int, int, int],
        alpha: float,
        trace: bool = False,
        thickness: float = 1.0,
    ) -> None:
        draw = ImageDraw.Draw(page.image)
        if direction == "rtl":
            pen = page.right - indent
            for unit in line:
                pen -= unit.width
                draw_glyphs(
                    page.image, unit.glyphs, pen, baseline, px, self.library, rgb, alpha, trace, thickness
                )
                if unit.underline and not unit.is_space:
                    y = int(baseline + px * 0.18)
                    draw.line((pen, y, pen + unit.width, y), fill=(*rgb, 200), width=max(1, int(round(thickness))))
        else:
            pen = page.left + indent
            for unit in line:
                draw_glyphs(
                    page.image, unit.glyphs, pen, baseline, px, self.library, rgb, alpha, trace, thickness
                )
                if unit.underline and not unit.is_space:
                    y = int(baseline + px * 0.18)
                    draw.line((pen, y, pen + unit.width, y), fill=(*rgb, 200), width=max(1, int(round(thickness))))
                pen += unit.width

    def _layout_grid(
        self,
        first: PageGeometry,
        units: list[Unit],
        request: RenderRequest,
        language: Language,
        px: float,
        ink: dict,
    ) -> list[Image.Image]:
        # One grapheme per cell, except Arabic-script words, which stay
        # joined and scale down to fit. A newline starts a new row.
        stream: list[Unit | None] = []
        for unit in units:
            if unit.is_break:
                stream.append(None)
            elif unit.is_space:
                continue
            elif unit.script == "Arab" or unit.script in CLUSTER_SCRIPTS or len(unit.text) <= 1:
                stream.append(unit)
            else:
                for cluster in regex.findall(r"\X", unit.text):
                    stream.append(self._reshape(cluster, unit.font_id, px))
        pages: list[Image.Image] = []
        page = first
        index = 0
        cursor = 0
        rgb = ink["rgb"]
        alpha = ink["alpha"]
        capacity = page.cols * page.rows

        def flush() -> None:
            nonlocal page, cursor
            self._stamp_page_number(page, len(pages) + 1, request.dpi)
            pages.append(page.image)
            font_cfg = self.registry.font(language.font)
            page = self._fresh_page(request, language, ink, px, font_cfg.line_mm)
            cursor = 0

        while index < len(stream):
            item = stream[index]
            if item is None:
                if cursor % page.cols:
                    cursor += page.cols - (cursor % page.cols)
                else:
                    cursor += page.cols
                index += 1
                if cursor >= capacity:
                    if len(pages) + 1 >= request.max_pages:
                        self._overflowed = True
                        flush()
                        return pages
                    flush()
                continue
            if cursor >= capacity:
                if len(pages) + 1 >= request.max_pages:
                    self._overflowed = True
                    flush()
                    return pages
                flush()
            row, col = divmod(cursor, page.cols)
            self._draw_cell(page, item, row, col, px, rgb, alpha, request.trace, request.thickness)
            cursor += 1
            index += 1
        flush()
        return pages

    def _draw_cell(
        self,
        page: PageGeometry,
        unit: Unit,
        row: int,
        col: int,
        px: float,
        rgb: tuple[int, int, int],
        alpha: float,
        trace: bool = False,
        thickness: float = 1.0,
    ) -> None:
        pad = int(px * 1.6)
        width = max(8, int(unit.width) + pad * 2)
        height = max(8, int(px * 3.2))
        scratch = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw_glyphs(scratch, unit.glyphs, pad, height * 0.62, px, self.library, rgb, alpha, trace, thickness)
        bbox = scratch.getbbox()
        if bbox is None:
            return
        crop = scratch.crop(bbox)
        cell = page.cell
        limit = cell - max(2, cell // 12)
        if crop.width > limit or crop.height > limit:
            scale = min(limit / crop.width, limit / crop.height)
            crop = crop.resize(
                (max(1, int(crop.width * scale)), max(1, int(crop.height * scale))),
                Image.Resampling.BICUBIC,
            )
        origin_x, origin_y = page.cell_origin(row, col)
        x = origin_x + (cell - crop.width) // 2
        y = origin_y + (cell - crop.height) // 2
        page.image.alpha_composite(crop, (x, y))
