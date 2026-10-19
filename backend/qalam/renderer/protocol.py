"""The seam a future stroke engine plugs into."""

from __future__ import annotations

from typing import Protocol

from qalam.models import RenderRequest, RenderResult


class HandwritingRenderer(Protocol):
    def render(self, request: RenderRequest) -> RenderResult:
        """Paint `request` onto one or more A4 pages.

        Pages are Pillow images. The web API only depends on this method.
        `NotebookRenderer` is the implementation the app calls: bundled fonts,
        contours cloned from a handwriting photo, or a later one-shot model
        can all satisfy it without changing routes or the client.
        """
