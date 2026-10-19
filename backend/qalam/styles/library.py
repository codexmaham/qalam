"""Preset styles on disk, plus handwriting and page photos kept for this process.

Uploads live in memory. Qalam is a single-user app on one computer, and a
preview should not re-send the photograph on every keystroke.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from qalam.registry import BACKEND_ROOT
from qalam.styles.config import DEFAULT_STYLE_ID
from qalam.styles.model import HandwritingStyle, StyleStats
from qalam.styles.pagephoto import PreparedPage

ASSETS = BACKEND_ROOT / "assets" / "handwriting-samples"

FONT_STYLE = HandwritingStyle(
    id="qalam-fonts",
    name="Qalam fonts",
    description="The bundled handwriting fonts, one for each script.",
    fallback_font="caveat",
    kind="font",
    stats=StyleStats(ink_rgb=(22, 54, 140)),
    note="Shaped with HarfBuzz. This is the multilingual path.",
)


class StyleLibrary:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ASSETS
        self.presets: dict[str, HandwritingStyle] = {}
        self.uploads: dict[str, HandwritingStyle] = {}
        self.pages: dict[str, PreparedPage] = {}
        self.reload()

    def reload(self) -> None:
        self.presets = {}
        if not self.root.exists():
            return
        for path in sorted(self.root.glob("*/style.json")):
            style = HandwritingStyle.load(path)
            self.presets[style.id] = style

    def known(self) -> list[HandwritingStyle]:
        styles = [FONT_STYLE]
        for style_id in ("school-neat", "cursive-letter", "quick-notes", "print-notes"):
            if style_id in self.presets:
                styles.append(self.presets[style_id])
        for style_id, style in self.presets.items():
            if style_id not in {item.id for item in styles}:
                styles.append(style)
        return styles

    @property
    def default_id(self) -> str:
        if DEFAULT_STYLE_ID in self.presets or DEFAULT_STYLE_ID == "qalam-fonts":
            return DEFAULT_STYLE_ID
        return "qalam-fonts"

    def resolve(self, style_id: str, handwriting_id: str = "") -> HandwritingStyle | None:
        """A sample style, or None when the page should use the font engine."""

        if handwriting_id:
            uploaded = self.uploads.get(handwriting_id)
            if uploaded is not None:
                return uploaded
        chosen = style_id or self.default_id
        if chosen == "qalam-fonts":
            return None
        style = self.presets.get(chosen)
        if style is None and chosen == self.default_id:
            return None
        if style is None:
            raise KeyError(f"Unknown handwriting style '{chosen}'")
        return style

    def remember_style(self, style: HandwritingStyle) -> str:
        style_id = secrets.token_hex(8)
        style.id = style_id
        self.uploads[style_id] = style
        if len(self.uploads) > 16:
            oldest = next(iter(self.uploads))
            self.uploads.pop(oldest, None)
        return style_id

    def remember_page(self, page: PreparedPage) -> str:
        page_id = secrets.token_hex(8)
        self.pages[page_id] = page
        if len(self.pages) > 8:
            oldest = next(iter(self.pages))
            self.pages.pop(oldest, None)
        return page_id

    def page(self, page_id: str) -> PreparedPage | None:
        if not page_id:
            return None
        found = self.pages.get(page_id)
        if found is None:
            raise KeyError("That page photo is no longer in memory. Upload it again.")
        return found
