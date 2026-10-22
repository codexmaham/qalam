"""Local HTTP API for the notebook renderer."""

from __future__ import annotations

import base64
import io
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from qalam import __version__
from qalam.models import RenderRequest
from qalam.notebook import NotebookRenderer
from qalam.practice import practice_for
from qalam.registry import INKS, MARGINS, PAGES, TEMPLATES, load_registry
from qalam.styles.config import DEFAULT_STYLE_ID
from qalam.styles.extract import analyse, ink_from_image, read_image
from qalam.styles.pagephoto import prepare_page
from qalam.styles.preview import glyph_strip
from qalam.styles.sheet import analyse_sheet, render_sheet
from qalam.voice import Transcript, VoiceError, WhisperTranscriber

PREVIEW_DPI = 108
PDF_DPI = 150
MAX_UPLOAD = 8 * 1024 * 1024
MAX_AUDIO = 25 * 1024 * 1024

registry = load_registry()
notebook = NotebookRenderer(registry)


class StyleDefaultIn(BaseModel):
    style: str = ""


class RenderIn(BaseModel):
    text: str = ""
    language: str
    template: str = "single-ruled"
    ink: str = "blue"
    name: str = ""
    date: str = ""
    max_pages: int = Field(default=8, ge=1, le=30)
    style: str = ""
    handwriting_id: str = ""
    page_photo_id: str = ""
    page_size: str = "a4"
    margin: str = "standard"
    class_name: str = ""
    thickness: float = 1.0
    trace: bool = False
    seed: int = 1
    variation: float = 0.4


def create_app(transcriber: WhisperTranscriber | None = None) -> FastAPI:
    app = FastAPI(title="Qalam", version=__version__)
    voice = transcriber or WhisperTranscriber()
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
        inks = [{"id": ink["id"], "name": ink["name"], "hex": ink["hex"]} for ink in INKS]
        inks.insert(0, {"id": "sample", "name": "Sample ink", "hex": "#2c2a28"})
        return {
            "languages": [item.to_public(registry.fonts) for item in registry.languages],
            "templates": [{k: t[k] for k in ("id", "name", "description")} for t in TEMPLATES],
            "inks": inks,
            "pages": PAGES,
            "margins": MARGINS,
            "default_style": notebook.styles.default_id,
        }

    @app.get("/api/styles")
    def styles() -> dict:
        return {
            "default": notebook.styles.default_id,
            "user_default": notebook.styles.user_default_id,
            "styles": [style.to_public() for style in notebook.styles.known()],
        }

    @app.get("/api/style-sheet")
    def style_sheet() -> Response:
        font = registry.font("caveat").path
        image = render_sheet(str(font))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return Response(
            content=buffer.getvalue(),
            media_type="image/png",
            headers={"Content-Disposition": 'attachment; filename="qalam-handwriting-sheet.png"'},
        )

    @app.post("/api/handwriting")
    async def handwriting(
        file: UploadFile = File(...),
        transcript: str = Form(""),
        mode: str = Form("notes"),
        name: str = Form("My handwriting"),
    ) -> dict:
        data = await _read_upload(file)
        try:
            image = read_image(data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        font = registry.font("caveat")
        try:
            if mode == "template":
                style = analyse_sheet(
                    image,
                    style_id="upload",
                    name=name.strip() or "My handwriting",
                    font_path=str(font.path),
                    fallback_font="caveat",
                )
            else:
                style = analyse(
                    image,
                    style_id="upload",
                    name=name.strip() or "My handwriting",
                    description="Handwriting measured from your photo.",
                    fallback_font="caveat",
                    font_path=str(font.path),
                    transcript=transcript,
                    sources=[],
                )
                if not style.glyphs:
                    style.stats.ink_rgb = ink_from_image(image)
                    style.note = (
                        "No letters were labeled. Type the transcript, or photograph the "
                        "handwriting sheet, to clone letters. New text uses Caveat in your ink."
                    )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not read that handwriting: {exc}") from exc
        style_id = notebook.styles.remember_style(style, make_default=True)
        public = style.to_public()
        public["id"] = style_id
        public["default"] = True
        public["message"] = "Your handwriting is now the default"
        strip = glyph_strip(style)
        if strip:
            public["preview"] = base64.b64encode(strip).decode("ascii")
        return public

    @app.post("/api/page-photo")
    async def page_photo(file: UploadFile = File(...)) -> dict:
        data = await _read_upload(file)
        try:
            prepared = prepare_page(data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        page_id = notebook.styles.remember_page(prepared)
        preview = _jpeg_preview(prepared)
        return {
            "id": page_id,
            "lines": len(prepared.lines),
            "empty": sum(1 for taken in prepared.occupied if not taken),
            "ruled": prepared.ruled,
            "note": prepared.note,
            "straightened": prepared.found_page,
            "preview": preview,
            "width": int(prepared.image.shape[1]),
            "height": int(prepared.image.shape[0]),
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
        return _pdf_response(result, body.language)

    @app.post("/api/png")
    def png(body: RenderIn) -> Response:
        result = _render(body, dpi=PDF_DPI, max_pages=min(max(body.max_pages, 1), 8))
        if not result.pages:
            raise HTTPException(status_code=500, detail="No pages rendered")
        if len(result.pages) == 1:
            buffer = io.BytesIO()
            result.pages[0].save(buffer, format="PNG", optimize=True)
            payload = buffer.getvalue()
            media = "image/png"
            filename = f"qalam-{body.language}.png"
        else:
            import zipfile

            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                for index, page in enumerate(result.pages, start=1):
                    page_buf = io.BytesIO()
                    page.save(page_buf, format="PNG", optimize=True)
                    archive.writestr(f"qalam-{index}.png", page_buf.getvalue())
            payload = buffer.getvalue()
            media = "application/zip"
            filename = f"qalam-{body.language}.zip"
        return Response(
            content=payload,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/api/style-default")
    def style_default(body: StyleDefaultIn) -> dict:
        try:
            chosen = notebook.styles.set_default(body.style)
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"default": chosen, "user_default": notebook.styles.user_default_id}

    @app.get("/api/practice")
    def practice(language: str, kind: str = "letters") -> dict:
        try:
            item = registry.language(language)
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return practice_for(language, kind, item.sample, list(item.recommended))

    @app.get("/api/voice")
    def voice_status() -> dict:
        return voice.status()

    @app.post("/api/transcribe")
    async def transcribe(file: UploadFile = File(...), language: str = Form("")) -> dict:
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="The recording was empty.")
        if len(data) > MAX_AUDIO:
            raise HTTPException(status_code=400, detail="That recording is larger than 25 MB.")
        suffix = Path(file.filename or "audio.webm").suffix.lower()
        known = {item.id for item in registry.languages}
        if language and language not in known:
            raise HTTPException(status_code=400, detail=f"Unknown language '{language}'.")
        try:
            result = voice.transcribe(data, suffix, language or None, known)
        except VoiceError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return _transcript_body(result)

    @app.get("/")
    def root() -> dict:
        return {
            "name": "Qalam",
            "tagline": "Speak it. See it handwritten. Print it.",
            "docs": "/docs",
            "ui": "http://127.0.0.1:5173",
        }

    return app


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The upload was empty.")
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status_code=400, detail="That image is larger than 8 MB.")
    return data


def _transcript_body(result: Transcript) -> dict:
    language = None
    if result.language_id:
        try:
            language = registry.language(result.language_id)
        except KeyError:
            language = None
    return {
        "text": result.text,
        "whisper_language": result.whisper_language,
        "language_id": result.language_id,
        "language_name": language.name if language else "",
        "direction": language.direction if language else "ltr",
        "template": language.recommended[0] if language and language.recommended else "single-ruled",
        "model": result.model,
    }


def _jpeg_preview(prepared) -> str:
    import cv2

    image = prepared.image
    height, width = image.shape[:2]
    scale = 480 / max(height, width)
    if scale < 1:
        image = cv2.resize(image, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
    if not ok:
        return ""
    return base64.b64encode(buf.tobytes()).decode("ascii")


def _pdf_response(result, language: str) -> Response:
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
    filename = f"qalam-{language}.pdf"
    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _render(body: RenderIn, dpi: int, max_pages: int):
    try:
        registry.language(body.language)
        template_ok = {item["id"] for item in TEMPLATES}
        ink_ok = {item["id"] for item in INKS} | {"sample"}
        if body.template not in template_ok:
            raise KeyError(f"Unknown template '{body.template}'")
        if body.ink not in ink_ok:
            raise KeyError(f"Unknown ink '{body.ink}'")
        if body.page_size not in {item["id"] for item in PAGES}:
            raise KeyError(f"Unknown page size '{body.page_size}'")
        if body.margin not in {item["id"] for item in MARGINS}:
            raise KeyError(f"Unknown margin '{body.margin}'")
        if body.style:
            notebook.styles.resolve(body.style, "")
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
        style_id=body.style,
        handwriting_id=body.handwriting_id,
        page_photo_id=body.page_photo_id,
        page_size=body.page_size,
        margin=body.margin,
        class_name=body.class_name,
        thickness=body.thickness,
        trace=body.trace,
        seed=body.seed,
        variation=body.variation,
    )
    try:
        return notebook.render(request)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Render failed: {exc}") from exc


def _mount_static(application: FastAPI) -> None:
    import os

    raw = os.environ.get("QALAM_STATIC", "").strip()
    root = Path(raw) if raw else Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if not (root / "index.html").is_file():
        return
    from fastapi.staticfiles import StaticFiles

    application.mount("/", StaticFiles(directory=root, html=True), name="ui")


app = create_app()
_mount_static(app)
