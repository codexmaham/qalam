"""Write the handwriting-style sample pages used in the README.

Run from the repo root, after `python3 scripts/build_presets.py`:

    python3 scripts/generate_style_samples.py
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from qalam.models import RenderRequest  # noqa: E402
from qalam.notebook import NotebookRenderer  # noqa: E402
from qalam.registry import FONTS_DIR  # noqa: E402
from qalam.styles.pagephoto import prepare_page  # noqa: E402
from qalam.styles.sheet import analyse_sheet, render_sheet  # noqa: E402

OUT = ROOT / "samples"
SOURCES = ROOT / "backend" / "assets" / "handwriting-samples" / "sources"


def _blank_notebook() -> bytes:
    """A photographed blank ruled page: perspective, paper grain, and a lamp gradient."""

    height, width = 1500, 1080
    yy, xx = np.mgrid[0:height, 0:width]
    paper = np.zeros((height, width, 3), np.float32)
    paper[:, :, 0] = 214
    paper[:, :, 1] = 228
    paper[:, :, 2] = 236
    light = 0.78 + 0.2 * (1 - yy / height) + 0.06 * (1 - xx / width)
    light += 0.04 * np.sin(yy / 180.0) 
    paper *= light[..., None]
    rng = np.random.default_rng(7)
    paper += rng.normal(0, 3.2, (height, width, 1))
    image = np.clip(paper, 0, 255).astype(np.uint8)
    for y in range(170, 1380, 54):
        wobble = int(6 * np.sin(y / 400.0))
        cv2.line(image, (120, y + wobble), (width - 90, y - wobble // 2), (176, 146, 92), 1)
    cv2.line(image, (168, 120), (162, height - 90), (78, 78, 176), 2)
    # Lay the page on a desk and tip it, the way a phone photo does.
    src = np.array([[90, 70], [width - 80, 40], [width - 40, height - 60], [50, height - 30]], np.float32)
    dst = np.array([[180, 120], [1180, 80], [1240, 1560], [80, 1500]], np.float32)
    matrix = cv2.getPerspectiveTransform(src, dst)
    canvas = np.full((1680, 1360, 3), 168, np.float32)
    canvas += rng.normal(0, 4, canvas.shape)
    canvas = np.clip(canvas, 0, 255).astype(np.uint8)
    warped = cv2.warpPerspective(image, matrix, (1360, 1680))
    mask = warped.sum(axis=2) > 30
    canvas[mask] = warped[mask]
    canvas = cv2.GaussianBlur(canvas, (3, 3), 0)
    ok, buf = cv2.imencode(".jpg", canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 86])
    if not ok:
        raise RuntimeError("Could not encode the blank notebook")
    return buf.tobytes()


def main() -> None:
    OUT.mkdir(exist_ok=True)
    renderer = NotebookRenderer()
    sentence = "The quick brown fox jumps over the lazy dog."
    pages = {
        "school-neat": "school-neat.png",
        "cursive-letter": "cursive-letter.png",
        "quick-notes": "quick-notes.png",
        "print-notes": "print-notes.png",
    }
    for style_id, filename in pages.items():
        result = renderer.render(
            RenderRequest(
                text=sentence,
                language_id="en",
                template_id="single-ruled",
                ink_id="sample",
                style_id=style_id,
                dpi=120,
                name="Amina",
                date="19 Oct 2026",
            )
        )
        result.pages[0].save(OUT / filename, format="PNG", optimize=True)
        print(filename, result.pages[0].size)

    blank = prepare_page(_blank_notebook())
    blank_id = renderer.styles.remember_page(blank)
    written = renderer.render(
        RenderRequest(
            text=(
                "Pack my box with five dozen liquor jugs. The quick brown fox jumps "
                "over the lazy dog, then sits down to finish the rest of the homework."
            ),
            language_id="en",
            ink_id="sample",
            style_id="school-neat",
            page_photo_id=blank_id,
            dpi=120,
        )
    )
    written.pages[0].save(OUT / "on-your-page.png", format="PNG", optimize=True)
    print(
        "on-your-page",
        written.pages[0].size,
        "pitch",
        round(blank.pitch, 4),
        "margin",
        round(blank.margin_x, 3),
        "first",
        round(blank.lines[0], 4) if blank.lines else None,
        "free",
        sum(not taken for taken in blank.occupied),
        blank.note,
    )

    photo = prepare_page((SOURCES / "style4-school-neat-a_32f2.jpg").read_bytes())
    page_id = renderer.styles.remember_page(photo)
    occupied = renderer.render(
        RenderRequest(
            text="This line starts after the notes already on the page.",
            language_id="en",
            ink_id="sample",
            style_id="school-neat",
            page_photo_id=page_id,
            dpi=120,
        )
    )
    occupied.pages[0].save(OUT / "on-your-page-occupied.png", format="PNG", optimize=True)
    print(
        "on-your-page-occupied",
        occupied.pages[0].size,
        "taken",
        sum(photo.occupied),
        "free",
        sum(not t for t in photo.occupied),
        "pen",
        photo.pen_rgb,
        "ruled",
        photo.ruled,
        photo.note,
    )

    font = str(FONTS_DIR / "PatrickHand-Regular.ttf")
    sheet = render_sheet(font, dpi=110)
    buffer = io.BytesIO()
    sheet.save(buffer, format="PNG")
    raw = cv2.imdecode(np.frombuffer(buffer.getvalue(), np.uint8), cv2.IMREAD_COLOR)
    from qalam.styles.sheet import write_guide_letters

    filled = write_guide_letters(raw, font)
    cv2.imwrite(str(OUT / "handwriting-sheet.png"), filled)
    style = analyse_sheet(filled, style_id="sheet", name="Sheet", font_path=font, fallback_font="patrick-hand")
    style_id = renderer.styles.remember_style(style)
    cloned = renderer.render(
        RenderRequest(
            text="Hello from my pen.",
            language_id="en",
            template_id="single-ruled",
            ink_id="sample",
            handwriting_id=style_id,
            dpi=120,
            name="Amina",
            date="19 Oct 2026",
        )
    )
    cloned.pages[0].save(OUT / "from-your-hand.png", format="PNG", optimize=True)
    print("from-your-hand", cloned.pages[0].size, "letters", len(style.glyphs))


if __name__ == "__main__":
    main()
