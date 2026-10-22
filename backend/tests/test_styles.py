"""Preset styles, the handwriting sheet, and photographed pages."""

from __future__ import annotations

import io
from pathlib import Path

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
    page = _page_rgb(result)
    new, _base = _new_ink(page, prepared)
    assert int(new.sum()) > 100
    pitch = max(8, int(round(prepared.pitch * page.shape[0])))
    baseline, _left, _lines = _first_line(new, pitch)
    free = [int(y * page.shape[0]) for y, taken in zip(prepared.lines, prepared.occupied) if not taken]
    taken_rows = [int(y * page.shape[0]) for y, taken in zip(prepared.lines, prepared.occupied) if taken]
    assert free and min(abs(baseline - row) for row in free) < pitch * 0.35
    assert min(abs(baseline - row) for row in taken_rows) > pitch * 0.45


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
    assert "empty" in photo.json()["note"] or "ruled" in photo.json()["note"]


def test_uploaded_hand_becomes_the_default(tmp_path, monkeypatch):
    from qalam.main import notebook

    library = StyleLibrary(data_dir=tmp_path)
    monkeypatch.setattr(notebook, "styles", library)
    image = np.full((120, 280, 3), 255, np.uint8)
    cv2.line(image, (30, 70), (220, 70), (25, 25, 30), 4)
    ok, buf = cv2.imencode(".png", image)
    assert ok
    uploaded = client.post(
        "/api/handwriting",
        files={"file": ("hand.png", buf.tobytes(), "image/png")},
        data={"transcript": "", "mode": "notes", "name": "My handwriting"},
    )
    assert uploaded.status_code == 200
    body = uploaded.json()
    assert body["message"] == "Your handwriting is now the default"
    assert body["default"] is True
    styles = client.get("/api/styles").json()
    assert styles["default"] == body["id"]
    assert styles["user_default"] == body["id"]
    reloaded = StyleLibrary(data_dir=tmp_path)
    assert reloaded.default_id == body["id"]
    assert reloaded.user_default_id == body["id"]
    assert reloaded.resolve(body["id"]).name == "My handwriting"
    page = NotebookRenderer(styles=reloaded).render(
        RenderRequest(text="Hello", language_id="en", handwriting_id=body["id"], ink_id="sample", dpi=72)
    )
    assert page.width > 100
    assert _ink_count(page.pages[0]) > 40
    cleared = client.post("/api/style-default", json={"style": "school-neat"})
    assert cleared.status_code == 200
    assert cleared.json()["default"] == "school-neat"
    assert cleared.json()["user_default"] == ""
    again = StyleLibrary(data_dir=tmp_path)
    assert again.default_id == "school-neat"
    assert again.user_default_id == ""
    assert (tmp_path / "handwriting" / f"{body['id']}.json").is_file()
    assert again.resolve("", body["id"]).id == body["id"]


LONG_PARAGRAPH = (
    "Pack my box with five dozen liquor jugs. The quick brown fox jumps "
    "over the lazy dog, then sits down to finish the rest of the homework."
)


def _blank_ruled_page() -> tuple[bytes, int, int]:
    """A straight ruled page. The first rule and the red margin are known."""

    height, width = 1100, 800
    image = np.full((height, width, 3), 244, np.uint8)
    first = 160
    for y in range(first, 1000, 48):
        cv2.line(image, (70, y), (width - 40, y), (190, 160, 110), 2)
    cv2.line(image, (100, 80), (100, height - 40), (70, 70, 190), 2)
    ok, buf = cv2.imencode(".png", image)
    assert ok
    return buf.tobytes(), first, 100


def _page_rgb(result) -> np.ndarray:
    return np.array(result.pages[0].convert("RGB"))


def _resized_photo(prepared, width: int, height: int) -> np.ndarray:
    rgb = cv2.cvtColor(prepared.image, cv2.COLOR_BGR2RGB)
    return np.array(Image.fromarray(rgb).resize((width, height), Image.Resampling.LANCZOS))


def _new_ink(page: np.ndarray, prepared) -> tuple[np.ndarray, np.ndarray]:
    base = _resized_photo(prepared, page.shape[1], page.shape[0])
    darker = base.astype(np.int16).mean(axis=2) - page.astype(np.int16).mean(axis=2)
    return darker > 25, base


def _existing_ink(base: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(base, cv2.COLOR_RGB2GRAY)
    paper = cv2.GaussianBlur(gray, (0, 0), max(2.0, gray.shape[0] * 0.01))
    darker = paper.astype(np.int16) - gray.astype(np.int16)
    ink = (darker > 24) & (gray < 155)
    red = base[:, :, 0].astype(np.int16)
    green = base[:, :, 1].astype(np.int16)
    blue = base[:, :, 2].astype(np.int16)
    red_px = (red > blue + 22) & (red > green + 12)
    blue_px = (blue > red + 18) & (gray > 90)
    ink = ink & ~red_px & ~blue_px
    mask = ink.astype(np.uint8) * 255
    bar = max(28, mask.shape[1] // 5)
    rules = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (bar, 1)))
    mask[cv2.dilate(rules, np.ones((3, 5), np.uint8)) > 0] = 0
    return mask > 0


def _visible_rules(base: np.ndarray) -> list[int]:
    gray = cv2.cvtColor(base, cv2.COLOR_RGB2GRAY)
    height, width = gray.shape
    x0, x1 = int(width * 0.22), int(width * 0.88)
    sobel = np.abs(cv2.Sobel(cv2.GaussianBlur(gray, (3, 3), 0), cv2.CV_32F, 0, 1, ksize=3))[:, x0:x1]
    covered = (sobel > np.percentile(sobel, 90)).mean(axis=1)
    rows = np.where(covered > 0.55)[0]
    if len(rows) == 0:
        return []
    groups: list[list[int]] = [[int(rows[0])]]
    for y in rows[1:]:
        if int(y) - groups[-1][-1] <= 3:
            groups[-1].append(int(y))
        else:
            groups.append([int(y)])
    lines = []
    limit = max(6, int(height * 0.015))
    for group in groups:
        if group[-1] - group[0] > limit:
            continue
        y = group[int(np.argmax(covered[group]))]
        if 0.03 < y / height < 0.97:
            lines.append(y)
    merged: list[int] = []
    for y in lines:
        if not merged or y - merged[-1] > height * 0.01:
            merged.append(y)
        else:
            merged[-1] = (merged[-1] + y) // 2
    return merged


def _red_x(base: np.ndarray) -> int:
    red = base[:, :, 0].astype(np.int16)
    green = base[:, :, 1].astype(np.int16)
    blue = base[:, :, 2].astype(np.int16)
    mask = (red > blue + 24) & (red > green + 14) & (base[:, :, 0] > 85)
    height, width = mask.shape
    column = mask[int(height * 0.08) : int(height * 0.92)].mean(axis=0)
    return int(np.argmax(column))


def _first_line(mask: np.ndarray, pitch: int) -> tuple[int, int, int]:
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    comps = []
    for comp in range(1, count):
        x, y, width, height, area = (int(v) for v in stats[comp])
        if area < 12 or height < 4 or width < 2:
            continue
        comps.append((x, y, width, height, y + height - 1))
    assert comps, "no new ink"
    top = min(item[1] for item in comps)
    line = [item for item in comps if item[1] < top + max(8, int(pitch * 0.72))]
    heights = np.array([item[3] for item in line])
    x_height = float(np.percentile(heights, 45))
    body = [item for item in line if 0.6 * x_height <= item[3] <= 1.45 * x_height]
    if len(body) < 3:
        body = line
    baseline = int(np.median([item[4] for item in body]))
    left = min(item[0] for item in line)
    centers = sorted(item[1] + item[3] / 2 for item in comps)
    lines = 1
    for prev, nxt in zip(centers, centers[1:]):
        if nxt - prev > pitch * 0.55:
            lines += 1
    return baseline, left, lines


def test_blank_ruled_page_baseline_is_the_first_rule():
    data, first_y, margin_x = _blank_ruled_page()
    prepared = prepare_page(data)
    assert prepared.ruled
    assert prepared.margin_x > 0.05
    renderer = NotebookRenderer()
    result = renderer.render(
        RenderRequest(
            text=LONG_PARAGRAPH,
            language_id="en",
            style_id="school-neat",
            ink_id="sample",
            page_photo_id=renderer.styles.remember_page(prepared),
            dpi=110,
        )
    )
    page = _page_rgb(result)
    new, base = _new_ink(page, prepared)
    rules = _visible_rules(base)
    assert len(rules) >= 5
    # The detector's first row is the rule that was drawn, in the PNG's pixel grid.
    expected = first_y / prepared.image.shape[0] * page.shape[0]
    assert abs(rules[0] - expected) < 6
    pitch = int(np.median(np.diff(rules)))
    baseline, left, line_count = _first_line(new, pitch)
    assert abs(baseline - rules[0]) <= 6
    red = _red_x(base)
    assert abs(red - margin_x / prepared.image.shape[1] * page.shape[1]) < 6
    assert left > red
    assert line_count >= 2
    existing = _existing_ink(base)
    overlap = int(np.logical_and(new, existing).sum())
    assert overlap / max(1, int(new.sum())) < 0.03


def test_new_ink_does_not_overlap_writing_already_on_the_page():
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
    result = renderer.render(
        RenderRequest(
            text="This starts on a free line and stays off the notes.",
            language_id="en",
            style_id="school-neat",
            ink_id="sample",
            page_photo_id=renderer.styles.remember_page(prepared),
            dpi=100,
        )
    )
    page = _page_rgb(result)
    new, base = _new_ink(page, prepared)
    existing = _existing_ink(base)
    assert int(new.sum()) > 200
    overlap = int(np.logical_and(new, existing).sum())
    assert overlap / int(new.sum()) < 0.03
    # The new line is below the handwriting, not on top of it.
    new_y = int(np.median(np.where(new)[0]))
    old_y = int(np.median(np.where(existing)[0]))
    assert new_y > old_y


def test_a_full_unruled_page_gets_no_new_ink():
    path = Path(__file__).resolve().parents[1] / "assets" / "handwriting-samples" / "sources" / "style4-school-neat-a_32f2.jpg"
    prepared = prepare_page(path.read_bytes())
    assert not prepared.ruled
    assert sum(1 for taken in prepared.occupied if not taken) == 0
    assert "No empty line" in prepared.note
    renderer = NotebookRenderer()
    result = renderer.render(
        RenderRequest(
            text="This line starts after the notes already on the page.",
            language_id="en",
            style_id="school-neat",
            ink_id="sample",
            page_photo_id=renderer.styles.remember_page(prepared),
            dpi=120,
        )
    )
    page = _page_rgb(result)
    new, base = _new_ink(page, prepared)
    existing = _existing_ink(base)
    assert int(existing.sum()) > 500
    assert int(new.sum()) < 40
    assert int(np.logical_and(new, existing).sum()) == 0
