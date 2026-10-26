"""Preset styles on disk, plus handwriting and page photos for this computer.

An uploaded hand is saved under the local data directory and becomes the
default for new pages, voice, and PDFs. Presets stay available.
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

from qalam.registry import BACKEND_ROOT
from qalam.styles.config import DEFAULT_STYLE_ID
from qalam.styles.model import HandwritingStyle, StyleStats
from qalam.styles.pagephoto import PreparedPage

ASSETS = BACKEND_ROOT / "assets" / "handwriting-samples"

STROKE_STYLE = HandwritingStyle(
    id="stroke-hand",
    name="Stroke hand",
    description="English written as pen strokes by a small recurrent network, with a new variation when you ask for one.",
    fallback_font="caveat",
    kind="sample",
    engine="strokes",
    stats=StyleStats(ink_rgb=(28, 36, 58)),
    note="Latin only. Urdu, Hindi, Arabic, Chinese and the other scripts stay on the bundled fonts.",
)

FONT_STYLE = HandwritingStyle(
    id="qalam-fonts",
    name="Qalam fonts",
    description="The bundled handwriting fonts, one for each script.",
    fallback_font="caveat",
    kind="font",
    stats=StyleStats(ink_rgb=(22, 54, 140)),
    note="Shaped with HarfBuzz. This is the multilingual path.",
)


def qalam_data_dir() -> Path:
    raw = os.environ.get("QALAM_DATA_DIR", "").strip()
    path = Path(raw).expanduser() if raw else Path.home() / ".local" / "share" / "qalam"
    path.mkdir(parents=True, exist_ok=True)
    return path


class StyleLibrary:
    def __init__(self, root: Path | None = None, data_dir: Path | None = None) -> None:
        self.root = root or ASSETS
        self.data_dir = data_dir if data_dir is not None else qalam_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.presets: dict[str, HandwritingStyle] = {}
        self.uploads: dict[str, HandwritingStyle] = {}
        self.pages: dict[str, PreparedPage] = {}
        self._user_default = ""
        self.reload()
        self._load_saved()

    def reload(self) -> None:
        self.presets = {}
        if not self.root.exists():
            return
        for path in sorted(self.root.glob("*/style.json")):
            style = HandwritingStyle.load(path)
            self.presets[style.id] = style

    def known(self) -> list[HandwritingStyle]:
        styles = [FONT_STYLE, STROKE_STYLE]
        for style_id in ("school-neat", "cursive-letter", "quick-notes", "print-notes"):
            if style_id in self.presets:
                styles.append(self.presets[style_id])
        for style_id, style in self.presets.items():
            if style_id not in {item.id for item in styles}:
                styles.append(style)
        styles.extend(self.uploads.values())
        return styles

    @property
    def default_id(self) -> str:
        saved = self._user_default
        if saved and (saved in self.uploads or saved in self.presets or saved in {"qalam-fonts", "stroke-hand"}):
            return saved
        if DEFAULT_STYLE_ID in self.presets or DEFAULT_STYLE_ID == "qalam-fonts":
            return DEFAULT_STYLE_ID
        return "qalam-fonts"

    @property
    def user_default_id(self) -> str:
        """The saved handwriting sample, when that sample is the default."""

        if self._user_default in self.uploads:
            return self._user_default
        return ""

    def resolve(self, style_id: str, handwriting_id: str = "") -> HandwritingStyle | None:
        """A sample style, or None when the page should use the font engine."""

        if handwriting_id:
            uploaded = self.uploads.get(handwriting_id)
            if uploaded is not None:
                return uploaded
        chosen = style_id or self.default_id
        if chosen in self.uploads:
            return self.uploads[chosen]
        if chosen == "stroke-hand":
            return STROKE_STYLE
        if chosen == "qalam-fonts":
            return None
        style = self.presets.get(chosen)
        if style is None and chosen == self.default_id:
            return None
        if style is None:
            raise KeyError(f"Unknown handwriting style '{chosen}'")
        return style

    def remember_style(self, style: HandwritingStyle, *, make_default: bool = False) -> str:
        style_id = secrets.token_hex(8)
        style.id = style_id
        self.uploads[style_id] = style
        if make_default:
            style.save(self.data_dir / "handwriting" / f"{style_id}.json")
            self._write_default(style_id)
        while len(self.uploads) > 16:
            oldest = next(iter(self.uploads))
            if oldest == self._user_default:
                oldest = next((item for item in self.uploads if item != self._user_default), oldest)
            self.uploads.pop(oldest, None)
        return style_id

    def set_default(self, style_id: str) -> str:
        """Pick a preset, or a saved hand, as the style for new pages."""

        if style_id == DEFAULT_STYLE_ID or style_id == "":
            self._write_default("")
            return self.default_id
        if style_id in self.uploads or style_id in self.presets or style_id in {"qalam-fonts", "stroke-hand"}:
            self._write_default(style_id)
            return self.default_id
        raise KeyError(f"Unknown handwriting style '{style_id}'")

    def _write_default(self, style_id: str) -> None:
        self._user_default = style_id
        path = self.data_dir / "default.json"
        path.write_text(json.dumps({"style_id": style_id}), encoding="utf-8")

    def _load_saved(self) -> None:
        folder = self.data_dir / "handwriting"
        if folder.exists():
            for path in sorted(folder.glob("*.json")):
                style = HandwritingStyle.load(path)
                self.uploads[style.id] = style
        pointer = self.data_dir / "default.json"
        if pointer.is_file():
            try:
                self._user_default = str(json.loads(pointer.read_text(encoding="utf-8")).get("style_id") or "")
            except (json.JSONDecodeError, OSError):
                self._user_default = ""

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
