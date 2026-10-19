"""The renderer the HTTP API talks to.

`qalam-fonts` delegates to the HarfBuzz engine. A sample style, including
one built from an upload, is drawn by the contour composer. A photographed
page replaces the blank template. A future one-shot model replaces the
composer and keeps this `render` method.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import replace

from PIL import Image

from qalam.models import RenderRequest, RenderResult
from qalam.registry import Registry, load_registry
from qalam.renderer.engine import FontHandwritingRenderer
from qalam.styles.compose import render_styled
from qalam.styles.library import StyleLibrary


class NotebookRenderer:
    def __init__(self, registry: Registry | None = None, styles: StyleLibrary | None = None) -> None:
        self.registry = registry or load_registry()
        self.fonts = FontHandwritingRenderer(self.registry)
        self.styles = styles or StyleLibrary()
        self._cache: dict[str, tuple[list[bytes], bool]] = {}

    def render(self, request: RenderRequest) -> RenderResult:
        style = self.styles.resolve(request.style_id, request.handwriting_id)
        photo = self.styles.page(request.page_photo_id)
        if style is None and photo is None:
            if request.ink_id == "sample":
                request = replace(request, ink_id="blue")
            return self.fonts.render(request)
        key = _key(request, style.id if style else "font", photo.image.shape if photo else ())
        cached = self._cache.get(key)
        if cached is not None:
            blobs, overflow = cached
            pages = [Image.open(io.BytesIO(blob)).convert("RGB") for blob in blobs]
            return RenderResult(
                pages=pages,
                truncated=overflow,
                width=pages[0].width if pages else 0,
                height=pages[0].height if pages else 0,
            )
        if style is None:
            # A photo with the bundled fonts: compose still needs a style for
            # spacing. Use an empty sample so every character takes the font path.
            from qalam.styles.model import HandwritingStyle, StyleStats

            style = HandwritingStyle(
                id="qalam-fonts",
                name="Qalam fonts",
                description="",
                fallback_font="caveat",
                kind="font",
                stats=StyleStats(),
            )
        result = render_styled(self.fonts, request, style, photo)
        blobs = []
        for page in result.pages:
            buf = io.BytesIO()
            page.save(buf, format="PNG", optimize=True)
            blobs.append(buf.getvalue())
        if len(self._cache) > 24:
            self._cache.clear()
        self._cache[key] = (blobs, result.truncated)
        return result


def _key(request: RenderRequest, style_id: str, shape) -> str:
    payload = "|".join(
        [
            request.text,
            request.language_id,
            request.template_id,
            request.ink_id,
            request.name,
            request.date,
            str(request.dpi),
            str(request.max_pages),
            style_id,
            request.handwriting_id,
            request.page_photo_id,
            str(shape),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
