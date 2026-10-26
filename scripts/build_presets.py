"""Build the bundled handwriting presets from the sample photographs.

Run from the repo root:

    python3 scripts/build_presets.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from qalam.registry import FONTS_DIR  # noqa: E402
from qalam.styles.extract import analyse, merge_styles, read_image  # noqa: E402

ASSETS = ROOT / "backend" / "assets" / "handwriting-samples"
SOURCES = ASSETS / "sources"
UPLOADS = Path("/home/ubuntu/.cursor/projects/workspace/uploads")

TRANSCRIPTS = {
    "style1": "\n".join(
        [
            "Dear Mom,",
            "I am having a great time",
            "at camp. The food is good",
            "and we have lots of fun",
            "activities. I miss you and",
            "can't wait to see you soon.",
            "Love,",
            "Alex",
        ]
    ),
    "style2": "\n".join(
        [
            "Today was a really good day.",
            "I woke up early and went for",
            "a walk before breakfast.",
            "The weather was perfect.",
            "I spent the afternoon reading",
            "and drinking coffee.",
            "Feeling grateful for the",
            "simple things.",
        ]
    ),
    "style3": "\n".join(
        [
            "Things to do today:",
            "- finish the report",
            "- email the team",
            "- pick up groceries",
            "- call mom",
            "- go for a run",
            "Notes:",
            "The meeting went well.",
            "We agreed on the new plan.",
        ]
    ),
    "style4": "\n".join(
        [
            "The quick brown fox jumps",
            "over the lazy dog. Pack",
            "my box with five dozen",
            "liquor jugs. How vexingly",
            "quick daft zebras jump!",
        ]
    ),
    "style5": "\n".join(
        [
            "The five boxing wizards",
            "jump quickly. Sphinx of",
            "black quartz, judge my vow.",
            "Two driven jocks help fax",
            "my big quiz.",
        ]
    ),
}

FILES = {
    "style1": "style1-black-cursive-letter_c9d1.jpg",
    "style2": "style2-blue-quick-notes_0b24.png",
    "style3": "style3-black-print-notes_b4aa.jpg",
    "style4": "style4-school-neat-a_32f2.jpg",
    "style5": "style5-school-neat-b_ef2e.jpg",
}


def main() -> None:
    SOURCES.mkdir(parents=True, exist_ok=True)
    for key, filename in FILES.items():
        src = UPLOADS / filename
        if not src.exists():
            src = SOURCES / filename
        if not src.exists():
            raise SystemExit(f"Missing sample photo {filename}")
        dest = SOURCES / filename
        if src.resolve() != dest.resolve():
            shutil.copyfile(src, dest)

    def build(key: str, style_id: str, name: str, description: str, font_id: str, font_file: str):
        image = read_image((SOURCES / FILES[key]).read_bytes())
        style = analyse(
            image,
            style_id=style_id,
            name=name,
            description=description,
            fallback_font=font_id,
            font_path=str(FONTS_DIR / font_file),
            transcript=TRANSCRIPTS[key],
            sources=[FILES[key]],
        )
        letters = sum(len(v) for v in style.glyphs.values())
        print(f"{style_id:16} chars {len(style.glyphs):3} variants {letters:4} ink {style.stats.ink_rgb} slant {style.stats.slant_deg:.1f}")
        return style

    cursive = build(
        "style1",
        "cursive-letter",
        "Black cursive letter",
        "A cursive letter in black ink. Cuts follow the transcript, so joined letters are approximate.",
        "caveat",
        "Caveat-wght.ttf",
    )
    quick = build(
        "style2",
        "quick-notes",
        "Blue quick notes",
        "Fast blue notes. Joined letters are split on the transcript, so some shapes are rough.",
        "caveat",
        "Caveat-wght.ttf",
    )
    printed = build(
        "style3",
        "print-notes",
        "Black print notes",
        "Upright print notes in black ink.",
        "patrick-hand",
        "PatrickHand-Regular.ttf",
    )
    school_a = build(
        "style4",
        "school-a",
        "School A",
        "",
        "patrick-hand",
        "PatrickHand-Regular.ttf",
    )
    school_b = build(
        "style5",
        "school-b",
        "School B",
        "",
        "patrick-hand",
        "PatrickHand-Regular.ttf",
    )
    school = merge_styles(
        [school_a, school_b],
        style_id="school-neat",
        name="Neat school notes",
        description="The same neat school hand, from two pages. This is the default until a new sample is set in config.py.",
    )
    school.note = (
        "Merged from two photographs of one neat school writer. "
        "Contours are stored from the pangrams. These photos slice letters roughly, "
        "so the page is set in the fallback handwriting font using the measured ink, slant, and spacing. "
        "Replace the photos before release if their licence is unclear."
    )
    print(f"{'school-neat':16} chars {len(school.glyphs):3} variants {sum(len(v) for v in school.glyphs.values()):4}")

    for style in (school, cursive, quick, printed):
        # The cuts from these photographs are not reliable enough to read.
        # The contours stay in the file; the page uses the measured ink and slant.
        style.engine = "stats"
        if style.id != "school-neat":
            style.note = (
                "Contours cut from the sample photo are stored in this file. "
                "Joined or crowded writing does not separate cleanly, so the page uses the "
                "fallback handwriting font in the sample's ink, with slant applied to the jitter. "
                "Photograph the handwriting sheet for letters taken from the pen itself."
            )
        path = ASSETS / style.id / "style.json"
        style.save(path)
        print("wrote", path, "bytes", path.stat().st_size)


if __name__ == "__main__":
    main()
