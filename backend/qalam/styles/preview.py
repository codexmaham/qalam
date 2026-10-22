"""A strip of the letters cut out of a handwriting sample."""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

from qalam.styles.compose import _raster
from qalam.styles.model import HandwritingStyle


def glyph_strip(style: HandwritingStyle, limit: int = 28) -> bytes | None:
    items = [(ch, variants[0]) for ch, variants in style.glyphs.items() if variants][:limit]
    if not items:
        return None
    cell = 72
    image = Image.new("RGB", (cell * len(items), cell + 28), (255, 252, 246))
    canvas = np.array(image)
    for index, (_ch, variant) in enumerate(items):
        raster = _raster(variant, x_height=36, scale_jitter=1)
        if raster is None:
            continue
        mask, baseline, origin = raster
        height, width = mask.shape
        x = index * cell + max(2, (cell - width) // 2) - origin
        y = 18 + 40 - baseline
        x0 = max(0, x)
        y0 = max(0, y)
        src_x = x0 - x
        src_y = y0 - y
        x1 = min(canvas.shape[1], x + width)
        y1 = min(canvas.shape[0], y + height)
        if x1 <= x0 or y1 <= y0:
            continue
        patch = mask[src_y : src_y + (y1 - y0), src_x : src_x + (x1 - x0)]
        ink = patch > 40
        canvas[y0:y1, x0:x1][ink] = (36, 40, 52)
    buf = io.BytesIO()
    Image.fromarray(canvas).save(buf, format="PNG")
    return buf.getvalue()
