"""Local HTTP API for the notebook renderer."""

from __future__ import annotations

import base64
import io

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from qalam import __version__
from qalam.models import RenderRequest
from qalam.registry import INKS, TEMPLATES, load_registry
from qalam.renderer import FontHandwritingRenderer

PREVIEW_DPI = 108
PDF_DPI = 150

registry = load_registry()
renderer = FontHandwritingRenderer(registry)


class RenderIn(BaseModel):
    text: str = ""
    language: str
    template: str = "single-ruled"
    ink: str = "blue"
    name: str = ""
    date: str = ""
    max_pages: int = Field(default=8, ge=1, le=30)


def create_app() -> FastAPI:
    app = FastAPI(title="Qalam", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:4173",
            "http://localhost:4173",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__, "languages": len(registry.languages)}

    @app.get("/api/languages")
    def languages() -> dict:
        return {
            "languages": [item.to_public(registry.fonts) for item in registry.languages],
            "templates": [{k: t[k] for k in ("id", "name", "description")} for t in TEMPLATES],
            "inks": [{"id": ink["id"], "name": ink["name"], "hex": ink["hex"]} for ink in INKS],
        }

    @app.post("/api/preview")
    def preview(body: RenderIn) -> dict:
        result = _render(body, dpi=PREVIEW_DPI, max_pages=min(body.max_pages, 8))
        encoded = []
        for page in result.pages:
            buffer = io.BytesIO()
            page.save(buffer, format="PNG", optimize=True)
            encoded.append(base64.b64encode(buffer.getvalue()).decode("ascii"))
        return {
            "pages": encoded,
            "page_count": len(encoded),
            "truncated": result.truncated,
            "width": result.width,
            "height": result.height,
        }

    @app.post("/api/pdf")
    def pdf(body: RenderIn) -> Response:
        result = _render(body, dpi=PDF_DPI, max_pages=min(max(body.max_pages, 1), 30))
        if not result.pages:
            raise HTTPException(status_code=500, detail="No pages rendered")
        buffer = io.BytesIO()
        result.pages[0].save(
            buffer,
            format="PDF",
            save_all=True,
            append_images=result.pages[1:],
            resolution=float(PDF_DPI),
        )
        filename = f"qalam-{body.language}.pdf"
        return Response(
            content=buffer.getvalue(),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/")
    def root() -> dict:
        return {
            "name": "Qalam",
            "tagline": "Speak it. See it handwritten. Print it.",
            "docs": "/docs",
            "ui": "http://127.0.0.1:5173",
        }

    return app


def _render(body: RenderIn, dpi: int, max_pages: int):
    try:
        registry.language(body.language)
        template_ok = {item["id"] for item in TEMPLATES}
        ink_ok = {item["id"] for item in INKS}
        if body.template not in template_ok:
            raise KeyError(f"Unknown template '{body.template}'")
        if body.ink not in ink_ok:
            raise KeyError(f"Unknown ink '{body.ink}'")
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    request = RenderRequest(
        text=body.text,
        language_id=body.language,
        template_id=body.template,
        ink_id=body.ink,
        name=body.name,
        date=body.date,
        dpi=dpi,
        max_pages=max_pages,
    )
    try:
        return renderer.render(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Render failed: {exc}") from exc


app = create_app()
