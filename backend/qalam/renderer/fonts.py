"""Font loading and HarfBuzz shaping."""

from __future__ import annotations

import threading
import unicodedata
from dataclasses import dataclass

import freetype
import uharfbuzz as hb

from qalam.registry import FontConfig, Registry
from qalam.renderer.jitter import ShapedGlyph


def _needs_glyph(ch: str) -> bool:
    if ch.isspace():
        return False
    category = unicodedata.category(ch)
    return category not in {"Mn", "Me", "Cf"}


@dataclass
class LoadedFont:
    config: FontConfig
    blob: hb.Blob
    face: hb.Face
    ft: freetype.Face
    unicodes: set[int]


class FontLibrary:
    """Lazy, process-wide font cache. FreeType faces are not thread-safe."""

    def __init__(self, registry: Registry) -> None:
        self.registry = registry
        self._loaded: dict[str, LoadedFont] = {}
        self._shape_cache: dict[tuple, tuple[ShapedGlyph, ...]] = {}
        self.lock = threading.Lock()

    def load(self, font_id: str) -> LoadedFont:
        cached = self._loaded.get(font_id)
        if cached is not None:
            return cached
        config = self.registry.font(font_id)
        blob = hb.Blob.from_file_path(str(config.path))
        face = hb.Face(blob)
        ft_face = freetype.Face(str(config.path))
        loaded = LoadedFont(
            config=config,
            blob=blob,
            face=face,
            ft=ft_face,
            unicodes=set(face.unicodes),
        )
        self._loaded[font_id] = loaded
        return loaded

    def covers(self, font_id: str, text: str) -> bool:
        loaded = self.load(font_id)
        for ch in text:
            if _needs_glyph(ch) and ord(ch) not in loaded.unicodes:
                return False
        return True

    def shape(self, font_id: str, text: str, px: float) -> list[ShapedGlyph]:
        key = (font_id, round(px, 2), text)
        cached = self._shape_cache.get(key)
        if cached is not None:
            return [ShapedGlyph(**vars(glyph)) for glyph in cached]
        loaded = self.load(font_id)
        font = hb.Font(loaded.face)
        scale = int(round(px * 64))
        font.scale = (scale, scale)
        if loaded.config.weight and loaded.face.has_var_data:
            font.set_variations({"wght": loaded.config.weight})
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(font, buf)
        glyphs = []
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            glyphs.append(
                ShapedGlyph(
                    font_id=font_id,
                    glyph_id=info.codepoint,
                    cluster=info.cluster,
                    x_advance=pos.x_advance / 64,
                    x_offset=pos.x_offset / 64,
                    y_offset=pos.y_offset / 64,
                )
            )
        if len(self._shape_cache) > 4000:
            self._shape_cache.clear()
        self._shape_cache[key] = tuple(glyphs)
        return [ShapedGlyph(**vars(glyph)) for glyph in glyphs]

    def prepare_freetype(self, font_id: str, px: float) -> freetype.Face:
        loaded = self.load(font_id)
        loaded.ft.set_char_size(int(round(px * 64)))
        if loaded.config.weight:
            try:
                loaded.ft.set_var_design_coords((loaded.config.weight,))
            except Exception:
                pass
        return loaded.ft
