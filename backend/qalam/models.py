"""Shared request and result types.

The HTTP layer and any future stroke-synthesis engine both speak these
types. Keep them free of FastAPI and Pillow imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RenderRequest:
    text: str
    language_id: str
    template_id: str = "single-ruled"
    ink_id: str = "blue"
    name: str = ""
    date: str = ""
    dpi: int = 150
    max_pages: int = 30
    style_id: str = ""
    handwriting_id: str = ""
    page_photo_id: str = ""


@dataclass
class RenderResult:
    pages: list = field(default_factory=list)
    truncated: bool = False
    width: int = 0
    height: int = 0
