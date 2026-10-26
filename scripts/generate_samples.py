"""Write the README sample pages.

Run from the repo root:

    python3 scripts/generate_samples.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from qalam.models import RenderRequest  # noqa: E402
from qalam.renderer import FontHandwritingRenderer  # noqa: E402

OUT = ROOT / "samples"
LABEL_FONT = ROOT / "frontend" / "public" / "fonts" / "Caveat-Regular.ttf"

SHEET = [
    ("en", "English"),
    ("vi", "Vietnamese"),
    ("ru", "Russian"),
    ("ar", "Arabic"),
    ("ur", "Urdu"),
    ("ps", "Pashto"),
    ("sd", "Sindhi"),
    ("hi", "Hindi"),
    ("pa-guru", "Punjabi (Gurmukhi)"),
    ("bn", "Bengali"),
    ("ta", "Tamil"),
    ("te", "Telugu"),
    ("gu", "Gujarati"),
    ("th", "Thai"),
    ("zh-hans", "Chinese"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
]


def render_page(renderer: FontHandwritingRenderer, language_id: str, template: str, **extra) -> Image.Image:
    language = renderer.registry.language(language_id)
    result = renderer.render(
        RenderRequest(
            text=language.sample,
            language_id=language_id,
            template_id=template,
            dpi=120,
            max_pages=1,
            **extra,
        )
    )
    return result.pages[0]


def ink_band(image: Image.Image) -> Image.Image:
    rgb = image.convert("RGB")
    pixels = rgb.load()
    rows = []
    for y in range(int(image.height * 0.07), int(image.height * 0.62)):
        dark = 0
        for x in range(40, image.width - 40, 3):
            r, g, b = pixels[x, y]
            if b < 165 and r < 185:
                dark += 1
        if dark > 4:
            rows.append(y)
    if not rows:
        return rgb.crop((0, 80, image.width, 220))
    top = max(0, rows[0] - 18)
    bottom = min(image.height, rows[0] + 130)
    return rgb.crop((0, top, image.width, bottom))


def specimen(renderer: FontHandwritingRenderer) -> Image.Image:
    label_font = ImageFont.truetype(str(LABEL_FONT), 32)
    width = 1100
    row_h = 128
    image = Image.new("RGB", (width, 56 + row_h * len(SHEET)), (255, 252, 246))
    draw = ImageDraw.Draw(image)
    draw.text((28, 12), "Qalam  ·  one line from each script", font=label_font, fill=(36, 28, 22))
    for index, (language_id, label) in enumerate(SHEET):
        language = renderer.registry.language(language_id)
        page = render_page(renderer, language_id, language.recommended[0])
        band = ink_band(page)
        y = 56 + index * row_h
        if index % 2 == 0:
            draw.rectangle((0, y, width, y + row_h), fill=(250, 245, 236))
        draw.text((24, y + 34), label, font=label_font, fill=(90, 62, 48))
        fitted = band.resize((740, max(1, int(band.height * 740 / band.width))), Image.Resampling.LANCZOS)
        max_h = row_h - 12
        if fitted.height > max_h:
            fitted = fitted.resize(
                (max(1, int(fitted.width * max_h / fitted.height)), max_h),
                Image.Resampling.LANCZOS,
            )
        paste_y = y + max(0, (row_h - fitted.height) // 2)
        image.paste(fitted, (320, paste_y))
    return image


def main() -> None:
    OUT.mkdir(exist_ok=True)
    renderer = FontHandwritingRenderer()
    pages = {
        "english-four-line.png": render_page(
            renderer, "en", "four-line", ink_id="blue", name="Amina", date="19 Oct 2026"
        ),
        "urdu-single-ruled.png": render_page(
            renderer, "ur", "single-ruled", ink_id="blue", name="آمنہ", date="19 Oct 2026"
        ),
        "arabic-single-ruled.png": render_page(renderer, "ar", "single-ruled", ink_id="navy"),
        "hindi-single-ruled.png": render_page(renderer, "hi", "single-ruled", ink_id="green"),
        "chinese-tianzige.png": render_page(renderer, "zh-hans", "tianzige", ink_id="black"),
        "japanese-square-grid.png": render_page(renderer, "ja", "square-grid", ink_id="blue"),
        "korean-square-grid.png": render_page(renderer, "ko", "square-grid", ink_id="red"),
    }
    for name, page in pages.items():
        path = OUT / name
        page.save(path, optimize=True)
        print(path.name, page.size)
    sheet = specimen(renderer)
    sheet.save(OUT / "scripts.png", optimize=True)
    print("scripts.png", sheet.size)


if __name__ == "__main__":
    main()
