# Contributing to Qalam

Qalam is a notebook for schools. The useful way to help is to add a language, a template, or a better handwriting face, and to keep the pages correct for that script.

## Set up

Python 3.11 or newer, and Node 20 or newer. Dependencies are wheels, including on an Apple Silicon Mac, so you do not need a compiler or a GPU.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m uvicorn qalam.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173. Tests:

```bash
cd backend
source .venv/bin/activate
pytest
```

Regenerate the pictures in `samples/`:

```bash
python3 scripts/generate_samples.py
```

Render a single page without the web app:

```bash
cd backend
python3 -m qalam.cli --language ur --template single-ruled --out page.png
```

## Where things live

| Path | What it is |
| --- | --- |
| `backend/languages.toml` | Every language and font. This is the file you edit to add a language. |
| `backend/fonts/` | The OFL font files, `OFL.txt`, and `NOTICE.md`. |
| `backend/qalam/renderer/` | Shaping, jitter, notebook templates, and the A4 page. |
| `backend/qalam/main.py` | The local HTTP API. |
| `frontend/src/` | The Notes page and the Voice placeholder. |

`FontHandwritingRenderer.render` is the function a future stroke-synthesis engine should replace. Routes, templates, and the web app only see `RenderRequest` and `RenderResult` in `backend/qalam/models.py`.

## Add a language

1. Choose a font you can redistribute. The SIL Open Font License is the expected choice. Put the file in `backend/fonts/`.
2. Add a `[fonts.your-id]` block to `backend/languages.toml`.
   - `file`, `family`
   - `style`: `handwriting`, or `text` when no handwriting face exists for that script
   - `scripts`: the scripts this font is really for, such as `Latn`, `Cyrl`, `Arab`, `Deva`, `Guru`, `Beng`, `Taml`, `Telu`, `Gujr`, `Thai`, `Hani`, `Hira`, `Kana`, `Hang`
   - `jitter`: how the letters are allowed to move
     - `glyph` — Latin and Cyrillic. Each letter shifts a little.
     - `cluster` — Indic and Thai. A base and its marks share one movement, so vowel signs stay attached.
     - `square` — Chinese, Japanese, and Korean. One character moves as a block.
     - `joining` — Arabic script, including Nastaliq. Only the whole word drifts. Per-letter scaling breaks the joins.
   - `jitter_amount`: about `0.3` to `1`
   - `line_mm` and `body_ratio`: line spacing and letter size on single-ruled paper. Nastaliq needs a taller line.
3. Add a `[[languages]]` block with `id`, English `name`, `native` name, `direction` (`ltr` or `rtl`), `script`, `family`, `font`, `fallbacks`, `recommended` templates, and a short `sample` in that language.
4. Add the font copyright to `backend/fonts/NOTICE.md`. If the font declares a Reserved Font Name, do not publish a modified version under that name.
5. Run `pytest`. A sample that shapes to a missing glyph (`.notdef`) fails the suite.
6. Run `python3 scripts/generate_samples.py` and read the page.

`fallbacks` is the font used when the primary face has no glyph. Latin words inside an Urdu note are drawn with Caveat, because Gulzar does not claim the Latin script. List `scripts` only for the writing systems the font is meant to draw.

## Templates

Templates are drawn in `backend/qalam/renderer/templates.py` and listed in `backend/qalam/registry.py`. A new template needs an `id` in both places and a branch in `make_page`. Grid templates put one grapheme in each cell. Arabic-script words stay whole so the letters keep joining, and the word is scaled to fit the cell.

## What not to depend on

Keep the app comfortable on an 8 GB machine. Prefer wheels over packages that compile. Do not add a network call to the render path. Audio and text stay on the computer.
