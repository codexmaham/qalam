"""The seam a future stroke engine plugs into."""

from __future__ import annotations

from typing import Protocol

from qalam.models import RenderRequest, RenderResult


class HandwritingRenderer(Protocol):
    def render(self, request: RenderRequest) -> RenderResult:
        """Paint `request` onto one or more A4 pages.

        Pages are Pillow images. The web API only depends on this method,
        so a stroke engine can replace the font renderer without touching
        routes, templates, or the client.
        """
