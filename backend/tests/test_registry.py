from qalam.registry import INKS, TEMPLATES, load_registry

REQUIRED = {
    "en",
    "ur",
    "ar",
    "hi",
    "pa-guru",
    "pa-arab",
    "ps",
    "sd",
    "bn",
    "fa",
    "es",
    "fr",
    "de",
    "pt",
    "it",
    "ru",
    "tr",
    "id",
    "zh-hans",
    "ja",
    "ko",
    "ta",
    "te",
    "mr",
    "gu",
    "th",
    "vi",
}


def test_required_languages_are_configured():
    registry = load_registry()
    ids = {item.id for item in registry.languages}
    missing = REQUIRED - ids
    assert not missing, missing
    assert len(registry.languages) >= 27


def test_every_language_points_at_a_real_font():
    registry = load_registry()
    for language in registry.languages:
        font = registry.font(language.font)
        assert font.path.is_file()
        assert language.direction in {"ltr", "rtl"}
        assert language.sample.strip()
        assert language.recommended
        for template_id in language.recommended:
            assert template_id in {item["id"] for item in TEMPLATES}
    assert {item["id"] for item in INKS} >= {"blue", "black", "pencil"}
