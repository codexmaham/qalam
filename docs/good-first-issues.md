# Good first issues

These are small, local, and do not need a GPU. Start with [CONTRIBUTING.md](../CONTRIBUTING.md).

1. **Add a practice sheet for a language that still uses the sample.**
   `backend/qalam/practice.py` has sheets for English, Urdu, Hindi, Arabic,
   Chinese, Japanese, and Korean. Another language falls back to its sample
   sentence. Add a `letters` and a `words` list, and name the paper in
   `recommended` for that language in `backend/languages.toml`.

2. **Add an ink colour.**
   Colours live in `INKS` in `backend/qalam/registry.py`. Add the id, a name,
   and an RGB triple, then click it on the Notes page.

3. **Fix a sample sentence.**
   Each language has a `sample` in `backend/languages.toml`. If a sentence is
   awkward, or a glyph is missing, change the sentence and run `pytest`. A
   missing glyph fails the suite.

4. **Label a template sketch.**
   The small paper previews are CSS classes in `frontend/src/styles.css`
   (`.sketch-graph`, `.sketch-urdu-copy`, and the others). A sketch that does
   not look like its paper is a one-file change.

5. **Document one font.**
   `backend/fonts/NOTICE.md` lists the copyright line for each face. If a
   block is thin, add the upstream project name and the license file, without
   changing the font binary.

6. **Thai line breaking, as a design note.**
   Thai currently wraps on grapheme clusters. A first issue here is a short
   comment or test that shows where a dictionary break would have to plug into
   `backend/qalam/renderer/segment.py`. Do not add a large dictionary in the
   first pull request.

Leave the stroke weights, the Whisper model, and the preset photographs
alone unless the maintainer asked you to replace them.
