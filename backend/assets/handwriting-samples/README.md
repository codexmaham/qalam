# Handwriting sample photographs

These pictures are the sources for the preset styles shipped with Qalam
(`school-neat`, `cursive-letter`, `quick-notes`, `print-notes`).

They were supplied as reference photos of five different hands. Styles 4 and 5
are the same neat school writer and are merged into `school-neat`. The photos
may have come from the internet. **Replace them with samples the maintainer
owns before a public release** if the licence is unclear. The extracted
contours in each `style.json` are derived from these files and should be
rebuilt afterwards:

```bash
python3 scripts/build_presets.py
```

The folder is separate from `backend/fonts/` on purpose. The fonts are SIL Open
Font License. These photographs are not.
