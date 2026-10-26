"""A handwriting style: measured letters plus the numbers that describe the hand.

Glyphs are stored as contours in x-height units, with y pointing up and
the origin on the baseline at the left of the ink. A later one-shot model
can fill the same structure, or ignore the contours and implement
`HandwritingRenderer` directly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GlyphVariant:
    width: float
    outers: list[list[list[float]]] = field(default_factory=list)
    holes: list[list[list[float]]] = field(default_factory=list)

    def to_json(self) -> dict:
        return {"w": round(self.width, 3), "o": self.outers, "h": self.holes}

    @classmethod
    def from_json(cls, raw: dict) -> GlyphVariant:
        return cls(width=float(raw["w"]), outers=raw.get("o") or [], holes=raw.get("h") or [])


@dataclass
class StyleStats:
    slant_deg: float = 0.0
    x_height_ratio: float = 0.45
    letter_spacing: float = 0.12
    word_spacing: float = 0.55
    stroke_width: float = 0.12
    ink_rgb: tuple[int, int, int] = (30, 30, 36)
    jitter_amount: float = 0.55

    def to_json(self) -> dict:
        return {
            "slant_deg": round(self.slant_deg, 2),
            "x_height_ratio": round(self.x_height_ratio, 3),
            "letter_spacing": round(self.letter_spacing, 3),
            "word_spacing": round(self.word_spacing, 3),
            "stroke_width": round(self.stroke_width, 3),
            "ink_rgb": list(self.ink_rgb),
            "jitter_amount": round(self.jitter_amount, 3),
        }

    @classmethod
    def from_json(cls, raw: dict | None) -> StyleStats:
        raw = raw or {}
        ink = raw.get("ink_rgb") or [30, 30, 36]
        return cls(
            slant_deg=float(raw.get("slant_deg", 0)),
            x_height_ratio=float(raw.get("x_height_ratio", 0.45)),
            letter_spacing=float(raw.get("letter_spacing", 0.12)),
            word_spacing=float(raw.get("word_spacing", 0.55)),
            stroke_width=float(raw.get("stroke_width", 0.12)),
            ink_rgb=(int(ink[0]), int(ink[1]), int(ink[2])),
            jitter_amount=float(raw.get("jitter_amount", 0.55)),
        )


@dataclass
class HandwritingStyle:
    id: str
    name: str
    description: str
    fallback_font: str
    kind: str = "sample"
    # "glyphs" draws the extracted contours. "stats" keeps those contours for
    # inspection but sets the page in the fallback font, tuned by the measurements.
    # Photo cuts that slice through joins are not readable; the sheet path is.
    engine: str = "glyphs"
    sources: list[str] = field(default_factory=list)
    stats: StyleStats = field(default_factory=StyleStats)
    glyphs: dict[str, list[GlyphVariant]] = field(default_factory=dict)
    note: str = ""

    def has_char(self, ch: str) -> bool:
        return bool(self.glyphs.get(ch))

    def to_public(self) -> dict:
        letters = sum(len(v) for v in self.glyphs.values())
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "kind": self.kind,
            "engine": self.engine,
            "fallback_font": self.fallback_font,
            "letters": letters,
            "characters": len(self.glyphs),
            "ink": "#{:02x}{:02x}{:02x}".format(*self.stats.ink_rgb),
            "stats": self.stats.to_json(),
            "note": self.note,
        }

    def save(self, path: Path) -> None:
        payload = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "fallback_font": self.fallback_font,
            "kind": self.kind,
            "engine": self.engine,
            "sources": self.sources,
            "note": self.note,
            "stats": self.stats.to_json(),
            "glyphs": {
                ch: [glyph.to_json() for glyph in variants]
                for ch, variants in sorted(self.glyphs.items())
            },
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> HandwritingStyle:
        raw = json.loads(path.read_text(encoding="utf-8"))
        glyphs = {
            ch: [GlyphVariant.from_json(item) for item in variants]
            for ch, variants in (raw.get("glyphs") or {}).items()
        }
        return cls(
            id=raw["id"],
            name=raw["name"],
            description=raw.get("description", ""),
            fallback_font=raw.get("fallback_font", "caveat"),
            kind=raw.get("kind", "sample"),
            engine=raw.get("engine", "glyphs"),
            sources=list(raw.get("sources") or []),
            note=raw.get("note", ""),
            stats=StyleStats.from_json(raw.get("stats")),
            glyphs=glyphs,
        )
