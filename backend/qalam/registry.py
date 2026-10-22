"""Load the pluggable language and font registry."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
LANGUAGES_PATH = BACKEND_ROOT / "languages.toml"
FONTS_DIR = BACKEND_ROOT / "fonts"

TEMPLATES: list[dict] = [
    {
        "id": "single-ruled",
        "name": "Single ruled",
        "description": "Classic notebook lines with a red margin.",
    },
    {
        "id": "four-line",
        "name": "Four-line copy",
        "description": "Ascender, dotted midline, baseline, and descender.",
    },
    {
        "id": "tianzige",
        "name": "Tianzige",
        "description": "Character squares with a cross, for Chinese practice.",
    },
    {
        "id": "square-grid",
        "name": "Square grid",
        "description": "Open squares for character practice.",
    },
    {
        "id": "urdu-copy",
        "name": "Urdu copy",
        "description": "Headline, dotted guide, and baseline for Urdu.",
    },
    {
        "id": "genko",
        "name": "Genkō yōshi",
        "description": "Japanese manuscript boxes with a center gutter.",
    },
    {
        "id": "wongoji",
        "name": "Wongoji",
        "description": "Korean manuscript squares with a red margin.",
    },
    {
        "id": "graph",
        "name": "Graph",
        "description": "Maths squares.",
    },
    {
        "id": "worksheet",
        "name": "Worksheet",
        "description": "Name, date, and class, then ruled lines.",
    },
]

PAGES = [
    {"id": "a4", "name": "A4"},
    {"id": "letter", "name": "US Letter"},
]
MARGINS = [
    {"id": "narrow", "name": "Narrow"},
    {"id": "standard", "name": "Standard"},
    {"id": "wide", "name": "Wide"},
]

INKS: list[dict] = [
    {"id": "blue", "name": "Ballpoint blue", "hex": "#16368C", "rgb": (22, 54, 140), "alpha": 0.96},
    {"id": "black", "name": "Black ink", "hex": "#1A1A1A", "rgb": (26, 26, 26), "alpha": 0.94},
    {"id": "navy", "name": "Navy", "hex": "#142033", "rgb": (20, 32, 51), "alpha": 0.95},
    {"id": "green", "name": "Green", "hex": "#1B5C3A", "rgb": (27, 92, 58), "alpha": 0.94},
    {"id": "red", "name": "Red pen", "hex": "#8E1E1A", "rgb": (142, 30, 26), "alpha": 0.94},
    {"id": "pencil", "name": "Pencil", "hex": "#4A4A4E", "rgb": (74, 74, 78), "alpha": 0.72},
]


@dataclass(frozen=True)
class FontConfig:
    id: str
    file: str
    family: str
    style: str
    jitter: str
    jitter_amount: float
    weight: float | None
    line_mm: float
    body_ratio: float
    scripts: tuple[str, ...]
    note: str

    @property
    def path(self) -> Path:
        return FONTS_DIR / self.file


@dataclass(frozen=True)
class Language:
    id: str
    name: str
    native: str
    direction: str
    script: str
    family: str
    font: str
    fallbacks: tuple[str, ...]
    recommended: tuple[str, ...]
    sample: str

    def to_public(self, fonts: dict[str, FontConfig]) -> dict:
        face = fonts[self.font]
        return {
            "id": self.id,
            "name": self.name,
            "native": self.native,
            "direction": self.direction,
            "script": self.script,
            "family": self.family,
            "sample": self.sample,
            "recommended": list(self.recommended),
            "font_family": face.family,
            "font_style": face.style,
            "font_note": face.note,
        }


@dataclass(frozen=True)
class Registry:
    fonts: dict[str, FontConfig]
    languages: list[Language]

    def language(self, language_id: str) -> Language:
        for item in self.languages:
            if item.id == language_id:
                return item
        known = ", ".join(item.id for item in self.languages)
        raise KeyError(f"Unknown language '{language_id}'. Known: {known}")

    def font(self, font_id: str) -> FontConfig:
        try:
            return self.fonts[font_id]
        except KeyError as exc:
            raise KeyError(f"Unknown font '{font_id}'") from exc


def _font(font_id: str, data: dict) -> FontConfig:
    weight = data.get("weight")
    return FontConfig(
        id=font_id,
        file=data["file"],
        family=data.get("family", font_id),
        style=data.get("style", "text"),
        jitter=data.get("jitter", "glyph"),
        jitter_amount=float(data.get("jitter_amount", 1)),
        weight=float(weight) if weight else None,
        line_mm=float(data.get("line_mm", 10)),
        body_ratio=float(data.get("body_ratio", 0.65)),
        scripts=tuple(data.get("scripts", [])),
        note=data.get("note", ""),
    )


def load_registry(path: Path | None = None) -> Registry:
    source = path or LANGUAGES_PATH
    with source.open("rb") as handle:
        raw = tomllib.load(handle)
    fonts = {font_id: _font(font_id, data) for font_id, data in raw.get("fonts", {}).items()}
    languages = []
    for item in raw.get("languages", []):
        languages.append(
            Language(
                id=item["id"],
                name=item["name"],
                native=item.get("native", item["name"]),
                direction=item.get("direction", "ltr"),
                script=item.get("script", "Latn"),
                family=item.get("family", "Other"),
                font=item["font"],
                fallbacks=tuple(item.get("fallbacks", [])),
                recommended=tuple(item.get("recommended", ["single-ruled"])),
                sample=item.get("sample", ""),
            )
        )
    missing = []
    for font in fonts.values():
        if not font.path.is_file():
            missing.append(font.file)
    if missing:
        raise FileNotFoundError("Missing font files: " + ", ".join(missing))
    for language in languages:
        if language.font not in fonts:
            raise KeyError(f"Language '{language.id}' uses unknown font '{language.font}'")
        for fallback in language.fallbacks:
            if fallback not in fonts:
                raise KeyError(f"Language '{language.id}' has unknown fallback '{fallback}'")
    return Registry(fonts=fonts, languages=languages)


def ink_by_id(ink_id: str) -> dict:
    for ink in INKS:
        if ink["id"] == ink_id:
            return ink
    raise KeyError(f"Unknown ink '{ink_id}'")


def template_by_id(template_id: str) -> dict:
    for template in TEMPLATES:
        if template["id"] == template_id:
            return template
    raise KeyError(f"Unknown template '{template_id}'")
