"""Page images: one render per script family, plus PDF and jitter."""

from qalam.models import RenderRequest
from qalam.registry import load_registry
from qalam.renderer import FontHandwritingRenderer
from qalam.renderer.templates import a4_px

FAMILIES = {
    "Latin": "en",
    "Vietnamese": "vi",
    "Cyrillic": "ru",
    "Arabic": "ar",
    "Nastaliq": "ur",
    "Pashto": "ps",
    "Sindhi": "sd",
    "Devanagari": "hi",
    "Gurmukhi": "pa-guru",
    "Bengali": "bn",
    "Tamil": "ta",
    "Telugu": "te",
    "Gujarati": "gu",
    "Thai": "th",
    "Chinese": "zh-hans",
    "Japanese": "ja",
    "Korean": "ko",
}


def _renderer():
    return FontHandwritingRenderer(load_registry())


def _ink_columns(image, y0, y1):
    pixels = image.load()
    left = image.width
    right = 0
    count = 0
    for y in range(y0, y1):
        for x in range(image.width):
            r, g, b = pixels[x, y][:3]
            if b < 170 and r < 190:
                count += 1
                left = min(left, x)
                right = max(right, x)
    return left, right, count


def test_each_script_family_renders_a_page():
    renderer = _renderer()
    dpi = 72
    expected = a4_px(dpi)
    for _family, language_id in FAMILIES.items():
        language = renderer.registry.language(language_id)
        result = renderer.render(
            RenderRequest(
                text=language.sample,
                language_id=language_id,
                template_id=language.recommended[0],
                ink_id="blue",
                dpi=dpi,
                max_pages=2,
            )
        )
        assert result.pages, language_id
        page = result.pages[0]
        assert (page.width, page.height) == expected
        _left, _right, count = _ink_columns(page, int(page.height * 0.08), int(page.height * 0.92))
        assert count > 30, language_id


def test_english_and_urdu_respect_margins_and_direction():
    renderer = _renderer()
    dpi = 96

    def centroid(language_id, template, text):
        result = renderer.render(
            RenderRequest(
                text=text,
                language_id=language_id,
                template_id=template,
                dpi=dpi,
            )
        )
        page = result.pages[0]
        pixels = page.load()
        total = 0
        weighted = 0
        y0, y1 = int(page.height * 0.08), int(page.height * 0.8)
        for y in range(y0, y1):
            for x in range(page.width):
                r, g, b = pixels[x, y]
                if b < 160 and r < 180:
                    total += 1
                    weighted += x
        assert total > 20, language_id
        return weighted / total, page.width

    en_x, width = centroid("en", "single-ruled", "Hi")
    ur_x, _ = centroid("ur", "single-ruled", "قلم")
    assert en_x < width * 0.45
    assert ur_x > width * 0.55


def test_long_text_is_a_multipage_pdf():
    renderer = _renderer()
    text = "The class wrote this line by hand.\n" * 45
    result = renderer.render(
        RenderRequest(text=text, language_id="en", template_id="single-ruled", dpi=72, max_pages=6)
    )
    assert len(result.pages) >= 2
    pdf, _truncated = renderer.render_pdf(
        RenderRequest(text=text, language_id="en", template_id="four-line", dpi=72, max_pages=4)
    )
    assert pdf.startswith(b"%PDF")
    page_objects = pdf.count(b"/Type /Page") - pdf.count(b"/Type /Pages")
    assert page_objects >= 2


def test_jitter_is_deterministic():
    request = RenderRequest(
        text="Same hand, same page.",
        language_id="en",
        template_id="four-line",
        ink_id="navy",
        name="Amina",
        date="19 Oct 2026",
        dpi=72,
    )
    registry = load_registry()
    first = FontHandwritingRenderer(registry).render(request).pages[0]
    second = FontHandwritingRenderer(registry).render(request).pages[0]
    assert first.tobytes() == second.tobytes()


def test_templates_and_inks_do_not_crash():
    renderer = _renderer()
    for template in ("single-ruled", "four-line", "tianzige", "square-grid"):
        result = renderer.render(
            RenderRequest(text="学", language_id="zh-hans", template_id=template, ink_id="green", dpi=72)
        )
        assert result.pages[0].width > 0
    result = renderer.render(
        RenderRequest(text="", language_id="en", template_id="single-ruled", ink_id="pencil", dpi=72)
    )
    assert result.pages
