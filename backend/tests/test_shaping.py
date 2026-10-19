"""Shaping checks, one assertion family per script."""

import pytest

from qalam.registry import load_registry
from qalam.renderer import FontHandwritingRenderer
from qalam.renderer.segment import segment

pytestmark = pytest.mark.usefixtures("renderer")


@pytest.fixture(scope="module")
def renderer():
    return FontHandwritingRenderer(load_registry())


def _glyphs(renderer, font_id, text, px=42):
    with renderer.library.lock:
        return renderer.library.shape(font_id, text, px)


def _advance_ids(glyphs):
    return [glyph.glyph_id for glyph in glyphs if glyph.x_advance > 0.5]


def test_no_missing_glyphs_in_any_sample(renderer):
    for language in renderer.registry.languages:
        with renderer.library.lock:
            chunks = [chunk for chunk in segment(language.sample) if chunk.strip()]
            for chunk in chunks:
                font_id = renderer.pick_font(chunk, language)
                glyphs = renderer.library.shape(font_id, chunk, 36)
                missing = [glyph for glyph in glyphs if glyph.glyph_id == 0]
                assert not missing, f"{language.id} / {chunk!r} shaped to .notdef"


def test_arabic_joins_instead_of_isolated_letters(renderer):
    isolated = _advance_ids(_glyphs(renderer, "aref-ruqaa-ink", "ب"))
    word = _glyphs(renderer, "aref-ruqaa-ink", "باب")
    initial = _advance_ids([glyph for glyph in word if glyph.cluster == 0])
    assert isolated and initial
    assert isolated[0] != initial[0]


def test_urdu_is_shaped_right_to_left(renderer):
    glyphs = _glyphs(renderer, "gulzar", "اردو")
    clusters = [glyph.cluster for glyph in glyphs]
    assert clusters[0] > clusters[-1]


def test_hindi_conjunct_becomes_one_glyph(renderer):
    glyphs = _glyphs(renderer, "kalam", "क्ष")
    assert len(glyphs) == 1
    assert len("क्ष") == 3


def test_bengali_conjunct_becomes_one_glyph(renderer):
    glyphs = _glyphs(renderer, "galada", "ক্ক")
    assert len(glyphs) == 1


def test_devanagari_matra_changes_the_glyph(renderer):
    base = _glyphs(renderer, "kalam", "ह")
    with_matra = _glyphs(renderer, "kalam", "हि")
    assert [glyph.glyph_id for glyph in base] != [glyph.glyph_id for glyph in with_matra]


def test_thai_mark_stays_attached(renderer):
    assert segment("กำ") == ["กำ"]
    glyphs = _glyphs(renderer, "sriracha", "กำ")
    assert any(glyph.x_advance == 0 for glyph in glyphs)


def test_chinese_wraps_per_character():
    units = [unit for unit in segment("学而时习之") if unit.strip()]
    assert units == ["学", "而", "时", "习", "之"]


def test_arabic_word_is_not_split():
    units = [unit for unit in segment("العلم نور") if not unit.isspace()]
    assert units == ["العلم", "نور"]


def test_latin_fallback_inside_urdu(renderer):
    language = renderer.registry.language("ur")
    assert renderer.pick_font("Hello", language) == "caveat"
    assert renderer.pick_font("اردو", language) == "gulzar"
