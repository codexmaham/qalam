"""Render one notebook from the command line.

    python -m qalam.cli --language ur --template single-ruled --text "علم" --out page.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

from qalam.models import RenderRequest
from qalam.renderer import FontHandwritingRenderer


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a Qalam notebook page.")
    parser.add_argument("--language", default="en")
    parser.add_argument("--template", default="single-ruled")
    parser.add_argument("--ink", default="blue")
    parser.add_argument("--text", default="")
    parser.add_argument("--name", default="")
    parser.add_argument("--date", default="")
    parser.add_argument("--dpi", type=int, default=120)
    parser.add_argument("--out", default="qalam-page.png")
    args = parser.parse_args()
    renderer = FontHandwritingRenderer()
    if not args.text:
        args.text = renderer.registry.language(args.language).sample
    result = renderer.render(
        RenderRequest(
            text=args.text,
            language_id=args.language,
            template_id=args.template,
            ink_id=args.ink,
            name=args.name,
            date=args.date,
            dpi=args.dpi,
        )
    )
    out = Path(args.out)
    result.pages[0].save(out)
    print(f"Wrote {out} ({result.width}x{result.height}, {len(result.pages)} page(s))")


if __name__ == "__main__":
    main()
