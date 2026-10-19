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
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from qalam.models import RenderRequest  # noqa: E402
from qalam.notebook import NotebookRenderer  # noqa: E402
from qalam.registry import FONTS_DIR  # noqa: E402
from qalam.styles.pagephoto import prepare_page  # noqa: E402
from qalam.styles.sheet import ORDER, _cells, analyse_sheet, render_sheet  # noqa: E402

OUT = ROOT / "samples"
SOURCES = ROOT / "backend" / "assets" / "handwriting-samples" / "sources"


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

    photo = prepare_page((SOURCES / "style4-school-neat-a_32f2.jpg").read_bytes())
    page_id = renderer.styles.remember_page(photo)
    written = renderer.render(
        RenderRequest(
            text="Pack my box with five dozen liquor jugs.",
            language_id="en",
            ink_id="black",
            style_id="school-neat",
            page_photo_id=page_id,
            dpi=120,
        )
    )
    written.pages[0].save(OUT / "on-your-page.png", format="PNG", optimize=True)
    print("on-your-page", written.pages[0].size)

    font = str(FONTS_DIR / "PatrickHand-Regular.ttf")
    sheet = render_sheet(font, dpi=110)
    buffer = io.BytesIO()
    sheet.save(buffer, format="PNG")
    raw = cv2.imdecode(np.frombuffer(buffer.getvalue(), np.uint8), cv2.IMREAD_COLOR)
    cells = _cells(raw)
    pil = Image.fromarray(cv2.cvtColor(raw, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    pen = ImageFont.truetype(font, 34)
    for index, (x, y, w, h) in enumerate(cells[: len(ORDER)]):
        ch = ORDER[index]
        box = pen.getbbox(ch)
        draw.text((x + 8, y + h * 0.22), ch, font=pen, fill=(25, 45, 130))
    filled = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
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
