"""Handwriting renderers.

`FontHandwritingRenderer` is the shipping engine: HarfBuzz shaping, a
little per-glyph jitter, notebook templates, and an A4 page image.
A stroke-synthesis engine can replace it by implementing `render`.
"""

from qalam.renderer.engine import FontHandwritingRenderer

__all__ = ["FontHandwritingRenderer"]
