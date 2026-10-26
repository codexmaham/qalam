"""Practice sheets, page sizes, stroke handwriting, and homework markup."""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from qalam.main import create_app
from qalam.models import RenderRequest
from qalam.notebook import NotebookRenderer
from qalam.renderer.templates import make_page, page_px
from qalam.styles.library import StyleLibrary
from qalam.styles.preview import glyph_strip

client = TestClient(create_app())


def _dark(image: Image.Image) -> np.ndarray:
    """Pen pixels, including ballpoint blue, excluding rules and the red margin."""
    arr = np.array(image.convert("RGB")).astype(int)
    red, green, blue = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    return (red < 80) & (green < 130) & (blue < 190) & ((red + green + blue) < 300)


def _render(**kwargs) -> Image.Image:
    request = RenderRequest(language_id="en", dpi=72, **kwargs)
    return NotebookRenderer().render(request).pages[0]


def test_page_sizes_margins_and_new_papers():
    a4_w, a4_h = page_px(72, "a4")
    letter_w, letter_h = page_px(72, "letter")
    assert letter_w > a4_w
    assert letter_h < a4_h
    narrow = np.array(make_page("single-ruled", 72, "ltr", 8, "a4", "narrow").image)
    wide = np.array(make_page("single-ruled", 72, "ltr", 8, "a4", "wide").image)
    red = lambda image: np.where(((image[:, :, 0] > 180) & (image[:, :, 2] < 130)).any(axis=0))[0]
    assert int(red(wide).min()) > int(red(narrow).min()) + 8
    graph = np.array(make_page("graph", 96, "ltr", 8).image.convert("RGB"))
    vertical = (np.abs(graph[:, 1:, 2].astype(int) - graph[:, :-1, 2].astype(int)) > 25).sum()
    assert vertical > 500
    genko = make_page("genko", 96, "ltr", 8)
    assert genko.cols == 20 and genko.gutter > 0
    wongoji = make_page("wongoji", 96, "ltr", 8)
    assert wongoji.cols == 10
    urdu = make_page("urdu-copy", 96, "rtl", 8)
    assert urdu.kind == "flow" and urdu.baselines()
    catalogue = client.get("/api/languages").json()
    ids = {item["id"] for item in catalogue["templates"]}
    assert {"urdu-copy", "genko", "wongoji", "graph", "worksheet"} <= ids
    assert {item["id"] for item in catalogue["pages"]} == {"a4", "letter"}


def test_tracing_is_lighter_and_practice_picks_the_paper():
    solid_page = _render(text="Trace this line.", template_id="four-line")
    dotted_page = _render(text="Trace this line.", template_id="four-line", trace=True)
    blank_page = _render(text="", template_id="four-line")
    solid = int(_dark(solid_page).sum())
    dotted = int(_dark(dotted_page).sum())
    assert solid > dotted
    dotted_arr = np.array(dotted_page.convert("RGB")).astype(int)
    blank_arr = np.array(blank_page.convert("RGB")).astype(int)
    assert int(np.abs(dotted_arr - blank_arr).sum()) > 400
    thin = int(_dark(_render(text="Pen", template_id="single-ruled", thickness=0.7, ink_id="black")).sum())
    thick = int(_dark(_render(text="Pen", template_id="single-ruled", thickness=1.8, ink_id="black")).sum())
    assert thick > thin
    english = client.get("/api/practice", params={"language": "en", "kind": "letters"})
    assert english.status_code == 200
    body = english.json()
    assert body["template"] == "four-line" and body["trace"] is True and "A a" in body["text"]
    urdu = client.get("/api/practice", params={"language": "ur", "kind": "words"}).json()
    assert urdu["template"] == "urdu-copy" and "قلم" in urdu["text"]
    chinese = client.get("/api/practice", params={"language": "zh-hans", "kind": "letters"}).json()
    assert chinese["template"] == "tianzige"


def test_homework_markup_and_worksheet_header():
    page = _render(
        text="# Rivers\n- Nile\n- Amazon\n---\nArea is x^2 and $1/2$ of the map.",
        template_id="worksheet",
        name="Amina",
        date="22 Oct",
        class_name="4B",
        ink_id="blue",
    )
    assert int(_dark(page).sum()) > 80
    # A markup rule is a long pen stroke, not three short dashes.
    rule = np.array(page.convert("RGB"))
    row_run = 0
    for row in rule:
        dark = (row[:, 0] < 80) & (row[:, 2] < 190)
        longest = current = 0
        for pixel in dark:
            current = current + 1 if pixel else 0
            longest = max(longest, current)
        row_run = max(row_run, longest)
    assert row_run > page.width * 0.45
    plain = _render(text="Hello", template_id="single-ruled", class_name="", ink_id="blue")
    headed = _render(text="Hello", template_id="worksheet", name="Amina", class_name="4B", ink_id="blue")
    assert headed.size == plain.size
    assert int(_dark(headed).sum()) > int(_dark(plain).sum())


def test_stroke_hand_varies_and_other_scripts_stay_on_fonts():
    styles = {item["id"] for item in client.get("/api/styles").json()["styles"]}
    assert "stroke-hand" in styles
    first = np.array(_render(text="Hello", style_id="stroke-hand", seed=1, ink_id="navy"))
    second = np.array(_render(text="Hello", style_id="stroke-hand", seed=2, ink_id="navy"))
    again = np.array(_render(text="Hello", style_id="stroke-hand", seed=1, ink_id="navy"))
    assert not np.array_equal(first, second)
    assert np.array_equal(first, again)
    assert int(((first[:, :, 0] < 80) & (first[:, :, 2] < 100)).sum()) > 40
    urdu = NotebookRenderer().render(
        RenderRequest(text="قلم", language_id="ur", style_id="stroke-hand", dpi=72, ink_id="black")
    )
    assert urdu.pages and int(_dark(urdu.pages[0]).sum()) > 30


def test_saved_hand_exposes_a_glyph_preview():
    library = StyleLibrary()
    school = library.presets["school-neat"]
    strip = glyph_strip(school)
    assert strip is not None and strip[:8] == b"\x89PNG\r\n\x1a\n"
    image = Image.open(__import__("io").BytesIO(strip))
    assert image.width > image.height
