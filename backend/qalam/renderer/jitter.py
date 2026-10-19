"""Deterministic, script-aware handwriting jitter.

Joining scripts (Arabic, Nastaliq) only drift the whole word, so
connections stay intact. Cluster scripts share one transform across a
base and its marks. Latin and Cyrillic move per glyph, with zero-advance
marks glued to the preceding base.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass


@dataclass
class ShapedGlyph:
    font_id: str
    glyph_id: int
    cluster: int
    x_advance: float
    x_offset: float
    y_offset: float
    scale: float = 1.0
    rotation: float = 0.0
    alpha: float = 1.0
    y_jitter: float = 0.0


def rng_for(*parts: str) -> random.Random:
    digest = hashlib.sha256("\u241f".join(parts).encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _group(glyphs: list[ShapedGlyph], profile: str) -> list[list[ShapedGlyph]]:
    if profile == "square" or profile == "joining":
        return [glyphs] if glyphs else []
    if profile == "cluster":
        groups: list[list[ShapedGlyph]] = []
        current: list[ShapedGlyph] = []
        current_id = None
        for glyph in glyphs:
            if current and glyph.cluster != current_id:
                groups.append(current)
                current = []
            current.append(glyph)
            current_id = glyph.cluster
        if current:
            groups.append(current)
        return groups
    groups = []
    current = []
    for glyph in glyphs:
        if glyph.x_advance == 0 and current:
            current.append(glyph)
            continue
        if current:
            groups.append(current)
        current = [glyph]
    if current:
        groups.append(current)
    return groups


def apply_jitter(
    glyphs: list[ShapedGlyph],
    profile: str,
    amount: float,
    em: float,
    rng: random.Random,
) -> None:
    """Mutate glyph positions in place. `amount` is 0..1 per font."""

    amount = max(0.0, min(amount, 1.5))
    if not glyphs or amount == 0:
        return
    if profile == "joining":
        drift = rng.uniform(-0.025, 0.025) * em * amount
        alpha = 1 - rng.random() * 0.08 * amount
        for glyph in glyphs:
            glyph.y_jitter = drift
            glyph.alpha = alpha
        return

    if profile == "square":
        rot = rng.uniform(-1.4, 1.4) * amount
        scale = 1 + rng.uniform(-0.04, 0.04) * amount
        drift = rng.uniform(-0.03, 0.03) * em * amount
        track = 1 + rng.uniform(-0.02, 0.03) * amount
        alpha = 1 - rng.random() * 0.1 * amount
        for glyph in glyphs:
            glyph.rotation = rot
            glyph.scale = scale
            glyph.y_jitter = drift
            glyph.alpha = alpha
            glyph.x_offset *= scale
            glyph.y_offset *= scale
            glyph.x_advance *= track
        return

    rot_span = (2.4 if profile == "glyph" else 0.8) * amount
    scale_span = (0.05 if profile == "glyph" else 0.03) * amount
    drift_span = (0.05 if profile == "glyph" else 0.03) * amount
    track_span = (0.04 if profile == "glyph" else 0.02) * amount
    for group in _group(glyphs, profile):
        rot = rng.uniform(-rot_span, rot_span)
        scale = 1 + rng.uniform(-scale_span, scale_span)
        drift = rng.uniform(-drift_span, drift_span) * em
        track = 1 + rng.uniform(-track_span, track_span)
        alpha = 1 - rng.random() * 0.12 * amount
        for glyph in group:
            glyph.rotation = rot
            glyph.scale = scale
            glyph.y_jitter = drift
            glyph.alpha = max(0.7, alpha)
            glyph.x_offset *= scale
            glyph.y_offset *= scale
            if glyph.x_advance:
                glyph.x_advance *= track
