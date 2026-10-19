"""Preset styles, the handwriting sheet, and photographed pages."""

from __future__ import annotations

import io

import cv2
import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from qalam.main import create_app
from qalam.models import RenderRequest
from qalam.notebook import NotebookRenderer
from qalam.styles.config import DEFAULT_STYLE_ID
from qalam.styles.library import StyleLibrary
from qalam.styles.pagephoto import prepare_page
from qalam.styles.sheet import ORDER, analyse_sheet, render_sheet

client = TestClient(create_app())


def _ink_count(image: Image.Image) -> int:
    arr = np.array(image.convert("RGB"))
    dark = (arr[:, :, 0] < 170) & (arr[:, :, 2] < 190)
    return int(dark.sum())


def test_default_style_is_one_config_line():
    assert DEFAULT_STYLE_ID == "school-neat"
    library = StyleLibrary()
    school = library.presets["school-neat"]
    assert school.engine == "stats"
    assert {"a", "e", "t", "o"} <= set(school.glyphs)
    assert library.presets["quick-notes"].stats.ink_rgb[2] > library.presets["quick-notes"].stats.ink_rgb[0]
    # Styles 4 and 5 are one writer, so the merged preset covers more letters.
    assert len(school.glyphs) >= len(library.presets["print-notes"].glyphs)


def test_preset_page_is_deterministic_and_has_ink():
    first = NotebookRenderer()
    second = NotebookRenderer()
    request = RenderRequest(
        text="Hello from the notebook.",
        language_id="en",
        template_id="single-ruled",
        ink_id="sample",
        style_id="school-neat",
        dpi=72,
        name="Noor",
        date="19 Oct 2026",
    )
    a = first.render(request)
    b = second.render(request)
    assert a.pages and _ink_count(a.pages[0]) > 80
    assert abs(a.width / a.height - 210 / 297) < 0.02
    buf_a, buf_b = io.BytesIO(), io.BytesIO()
    a.pages[0].save(buf_a, format="PNG")
    b.pages[0].save(buf_b, format="PNG")
    assert buf_a.getvalue() == buf_b.getvalue()


def test_missing_letters_and_arabic_still_render():
    renderer = NotebookRenderer()
    request = RenderRequest(
        text="Hello from the notebook.\nالعلم نور.",
        language_id="en",
        template_id="four-line",
        ink_id="blue",
        style_id="school-neat",
        dpi=72,
    )
    result = renderer.render(request)
    assert result.pages
    assert _ink_count(result.pages[0]) > 40
    fonts = renderer.render(RenderRequest(text="Hello", language_id="en", style_id="qalam-fonts", dpi=72))
    assert fonts.pages


def test_handwriting_sheet_round_trip():
    from qalam.registry import FONTS_DIR

    font = str(FONTS_DIR / "PatrickHand-Regular.ttf")
    sheet = render_sheet(font, dpi=110)
    buffer = io.BytesIO()
    sheet.save(buffer, format="PNG")
    image = cv2.imdecode(np.frombuffer(buffer.getvalue(), np.uint8), cv2.IMREAD_COLOR)
    from qalam.styles.sheet import _cells

    cells = _cells(image)
    assert len(cells) == len(ORDER)
    from qalam.styles.sheet import write_guide_letters

    filled = write_guide_letters(image, font)
    style = analyse_sheet(filled, style_id="sheet", name="Sheet", font_path=font, fallback_font="patrick-hand")
    assert {"H", "e", "o", "m", "y"} <= set(style.glyphs)

    def _span(ch: str) -> tuple[float, float]:
        glyph = style.glyphs[ch][0]
        ys = [point[1] for ring in glyph.outers + glyph.holes for point in ring]
        return min(ys), max(ys)

    for ch in ("e", "o", "m"):
        bottom, top = _span(ch)
        assert -0.2 <= bottom <= 0.2
        assert 0.75 <= top - bottom <= 1.3
    m_bottom, m_top = _span("m")
    o_bottom, o_top = _span("o")
    assert abs((m_top - m_bottom) - (o_top - o_bottom)) < 0.25
    y_bottom, y_top = _span("y")
    assert y_bottom < -0.15
    assert y_top > 0.7
    renderer = NotebookRenderer()
    style_id = renderer.styles.remember_style(style)
    page = renderer.render(
        RenderRequest(
            text="Hello",
            language_id="en",
            ink_id="sample",
            handwriting_id=style_id,
            dpi=72,
        )
    )
    assert _ink_count(page.pages[0]) > 40


def _warped_ruled_page() -> bytes:
    height, width = 900, 640
    image = np.full((height, width, 3), 245, np.uint8)
    for y in range(120, 820, 48):
        cv2.line(image, (70, y), (width - 40, y), (170, 190, 220), 2)
    cv2.line(image, (90, 80), (90, height - 40), (80, 80, 200), 3)
    src = np.array([[40, 30], [600, 20], [620, 860], [30, 870]], np.float32)
    dst = np.array([[80, 60], [700, 40], [760, 980], [20, 940]], np.float32)
    matrix = cv2.getPerspectiveTransform(src, dst)
    canvas = np.full((1040, 820, 3), 180, np.uint8)
    warped = cv2.warpPerspective(image, matrix, (820, 1040))
    mask = warped.sum(axis=2) > 0
    canvas[mask] = warped[mask]
    ok, buf = cv2.imencode(".png", canvas)
    assert ok
    return buf.tobytes()


def test_uploaded_page_is_straightened_and_written_on():
    prepared = prepare_page(_warped_ruled_page())
    assert len(prepared.lines) >= 5
    renderer = NotebookRenderer()
    page_id = renderer.styles.remember_page(prepared)
    result = renderer.render(
        RenderRequest(
            text="Hello on my page.",
            language_id="en",
            style_id="school-neat",
            ink_id="black",
            page_photo_id=page_id,
            dpi=80,
        )
    )
    page = result.pages[0]
    assert abs(page.width / page.height - 210 / 297) < 0.02
    arr = np.array(page)
    gray = arr.mean(axis=2)
    dark = gray < 90
    assert dark.sum() > 30
    # New writing should sit near a detected rule, not in the margin.
    rows = dark.sum(axis=1)
    peak = int(rows.argmax())
    line_rows = [int(y * page.height) for y in prepared.lines]
    assert min(abs(peak - row) for row in line_rows) < 48


def test_writing_skips_lines_that_already_have_ink():
    height, width = 980, 700
    image = np.full((height, width, 3), 246, np.uint8)
    rules = list(range(150, 900, 52))
    for y in rules:
        cv2.line(image, (80, y), (width - 50, y), (186, 168, 118), 2)
    cv2.line(image, (110, 90), (110, height - 40), (70, 70, 190), 2)
    for y in rules[:3]:
        cv2.putText(image, "already on this line", (150, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (45, 40, 35), 2)
    ok, buf = cv2.imencode(".png", image)
    assert ok
    prepared = prepare_page(buf.tobytes())
    assert any(prepared.occupied)
    assert any(not taken for taken in prepared.occupied)
    renderer = NotebookRenderer()
    page_id = renderer.styles.remember_page(prepared)
    result = renderer.render(
        RenderRequest(
            text="This starts on a free line.",
            language_id="en",
            style_id="school-neat",
            ink_id="sample",
            page_photo_id=page_id,
            dpi=90,
        )
    )
    page = np.array(result.pages[0])
    photo = cv2.resize(prepared.image, (page.shape[1], page.shape[0]), interpolation=cv2.INTER_AREA)
    photo = cv2.cvtColor(photo, cv2.COLOR_BGR2RGB)
    changed = np.abs(page.astype(np.int16) - photo.astype(np.int16)).sum(axis=2) > 50
    rows = np.where(changed.sum(axis=1) > 15)[0]
    assert len(rows) > 0
    top = int(rows.min())
    pitch = prepared.pitch * page.shape[0]
    free = [int(y * page.shape[0]) for y, taken in zip(prepared.lines, prepared.occupied) if not taken]
    taken_rows = [int(y * page.shape[0]) for y, taken in zip(prepared.lines, prepared.occupied) if taken]
    assert free and min(abs(top - row) for row in free) < pitch * 1.3
    assert min(abs(top - row) for row in taken_rows) > pitch * 0.35


def test_styles_api_and_uploads():
    styles = client.get("/api/styles")
    assert styles.status_code == 200
    body = styles.json()
    assert body["default"] == "school-neat"
    assert {item["id"] for item in body["styles"]} >= {"qalam-fonts", "school-neat", "quick-notes", "print-notes", "cursive-letter"}
    sheet = client.get("/api/style-sheet")
    assert sheet.status_code == 200
    assert sheet.content[:8] == b"\x89PNG\r\n\x1a\n"
    photo = client.post("/api/page-photo", files={"file": ("page.png", _warped_ruled_page(), "image/png")})
    assert photo.status_code == 200
    page_id = photo.json()["id"]
    assert photo.json()["lines"] >= 5
    preview = client.post(
        "/api/preview",
        json={"text": "On the photo.", "language": "en", "style": "school-neat", "ink": "black", "page_photo_id": page_id},
    )
    assert preview.status_code == 200
    assert preview.json()["page_count"] == 1
    png = client.post("/api/png", json={"text": "On the photo.", "language": "en", "page_photo_id": page_id, "ink": "black"})
    assert png.status_code == 200
    assert png.content[:8] == b"\x89PNG\r\n\x1a\n"
