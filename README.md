# Qalam

**Speak it. See it handwritten. Print it.**

Qalam (قلم, a pen) turns a lesson into a notebook page. You type or paste the text, pick a language and a paper, and print an A4 PDF. The writing is shaped properly for each script, then nudged a little so it does not look like a font stamped in a straight line.

It runs on the school computer. Nothing is uploaded. A MacBook Air with 8 GB of memory is enough.

You can type the lesson, or speak it. Whisper transcribes on the same machine, and the page you already see is the page it writes.

![English four-line copy page](samples/english-four-line.png)

## What you can do today

- Type or paste text and watch a notebook page update.
- Choose a language. Right-to-left scripts are set right to left, and complex scripts are shaped with HarfBuzz, not drawn character by character.
- Pick the paper: single-ruled, four-line English copy, tianzige (the Chinese character grid), or an open square grid in the spirit of genkō yōshi and wongoji.
- Pick an ink: ballpoint blue, black, navy, green, red, or pencil.
- Put a name and a date on the sheet.
- Download a multi-page A4 PDF, or a PNG of the page.
- Pick a handwriting style. The default is the neat school hand. Change it with one line in [`backend/qalam/styles/config.py`](backend/qalam/styles/config.py): `DEFAULT_STYLE_ID`.
- Upload a photo of your own page. Qalam straightens it, finds the ruled lines, and writes on the empty ones. A full page is left as it is.
- Upload a handwriting sample, or fill the printed template sheet, and new text is set from that hand. The upload becomes your default immediately, for Notes, Voice, and PDF, and it is kept in `~/.local/share/qalam`.
- Record a lesson, or upload an audio file. Whisper transcribes it on this computer and the notebook writes the page.
- Add a language by adding a font and a block of config. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Handwriting styles

The page can be set in a bundled font, or in a style measured from a photograph. Both go through the same `render` method, so a one-shot handwriting model can replace the contour composer later without changing the page or the API.

| Style | What it is |
| --- | --- |
| Neat school notes | The default. Two pages of one neat school writer, merged. |
| Black cursive letter | A cursive letter in black ink. |
| Blue quick notes | Fast notes in blue. |
| Black print notes | Upright print in black. |
| Qalam fonts | The original multilingual fonts, one per script. |

![Neat school notes, the default](samples/school-neat.png)

![Blue quick notes](samples/quick-notes.png)

![Black cursive letter](samples/cursive-letter.png)

![Black print notes](samples/print-notes.png)

An uploaded sample is saved on this computer and selected for every new page until you choose **Use Neat school notes**. The preset itself stays the one line in `config.py`; your hand is a file next to it, not a change to that line.

**What quality to expect.** A photo of ordinary notes does not give clean, separable letters, especially when the writing is joined. Qalam still cuts the photo into contours and stores them, and it measures slant, x-height, letter spacing, stroke width, and ink colour. Those numbers tune the fallback font: the page is set in the closest bundled handwriting face, in the sample's ink, with the slant leaning the jitter. That is an honest limit of a CPU pipeline on an 8 GB machine, not a neural one-shot model.

The reliable way to use your own letters is the **handwriting sheet**. Print it, write one character in each box, and photograph it. Each box is one glyph. Letters are normalised to one shared x-height and one baseline, by their class: x-height letters, ascenders, and descenders. A contour that is the wrong size, a merged blob, or a piece of the box is dropped, and that character is set from the bundled font at the same size.

![A filled handwriting sheet](samples/handwriting-sheet.png)

![The same letters set as a new sentence](samples/from-your-hand.png)

## Your own page

Leave the paper blank and you get a white A4 sheet with the usual rules. Upload a photo of a notebook page and that photo becomes the paper. Qalam straightens the perspective and finds the ruled lines. Handwriting sits on those rules, baseline on the line, starting just to the right of the red margin, and the x-height is fitted to the gap. Lines that already contain pen ink are skipped. On a page with no rules, the line spacing is taken from the writing already there, and new text is placed only where a whole line is empty, usually below the last ink. When the page is full, nothing new is written and the note says so. The ink is the pen already on the page, or the style's ink when the page is blank, with a little grain and variation in the stroke so it reads as a pen. Download the result as a PNG or a PDF.

![A paragraph on a photographed blank page, on the rules and inside the margin](samples/on-your-page.png)

![A page that is already full, so nothing new is written](samples/on-your-page-occupied.png)

The preset photographs live in [`backend/assets/handwriting-samples/`](backend/assets/handwriting-samples/README.md), separate from the fonts. They may have come from the internet. Replace them with samples the maintainer owns before a public release if the licence is unclear, then run `python3 scripts/build_presets.py`.

## Voice

On the Voice page, press **Record** and speak, then **Stop**. A live waveform shows that the microphone is open. You can also upload a wav, mp3, m4a, ogg, or webm file. The transcript appears in an editable box. Whisper picks the language, Qalam maps it onto the notebook's language and paper (Chinese becomes the simplified-Chinese setting, Punjabi becomes Gurmukhi unless you chose Shahmukhi yourself, Filipino comes from Whisper's Tagalog code), and the same handwriting renderer writes the page. Download the A4 PDF from there.

Speech stays on this computer. The engine is [faster-whisper](https://github.com/SYSTRAN/faster-whisper), which is Whisper running through CTranslate2. It uses one CPU thread at int8, so an 8 GB MacBook Air M1 can keep the browser open beside it, and a short recording is not dropped or repeated. The default model is the multilingual **base** (about 150 MB). The first transcription downloads it into `~/.cache/qalam/whisper`. Later runs are offline.

```bash
# optional, before you start the API
export QALAM_WHISPER_MODEL=base   # tiny, base, or small
export QALAM_WHISPER_DIR="$HOME/.cache/qalam/whisper"
```

`tiny` is faster and less accurate. `small` is the better choice when the machine has room. English-only weights (names ending in `.en`) are refused, because the notebook is multilingual. ffmpeg has to be installed (`brew install ffmpeg` on a Mac) so a browser recording can be turned into 16 kHz mono audio. `pip install -r requirements.txt` installs faster-whisper; no compiler is required.

![Urdu in Nastaliq on ruled paper](samples/urdu-single-ruled.png)

![Simplified Chinese on a tianzige grid](samples/chinese-tianzige.png)

![One line from each script family](samples/scripts.png)

## Languages

42 languages render in this version. “Handwriting” means an open handwriting, brush, or pen face. “Text face” means we could not find an open handwriting font that covers the script, so the page uses a text face and says so.

| Language | Native | Script | Direction | Font | Kind |
| --- | --- | --- | --- | --- | --- |
| English | English | Latin | LTR | Caveat | Handwriting |
| Spanish | Español | Latin | LTR | Caveat | Handwriting |
| French | Français | Latin | LTR | Caveat | Handwriting |
| German | Deutsch | Latin | LTR | Caveat | Handwriting |
| Portuguese | Português | Latin | LTR | Caveat | Handwriting |
| Italian | Italiano | Latin | LTR | Caveat | Handwriting |
| Turkish | Türkçe | Latin | LTR | Caveat | Handwriting |
| Indonesian | Bahasa Indonesia | Latin | LTR | Caveat | Handwriting |
| Vietnamese | Tiếng Việt | Latin | LTR | Patrick Hand | Handwriting |
| Dutch | Nederlands | Latin | LTR | Caveat | Handwriting |
| Polish | Polski | Latin | LTR | Caveat | Handwriting |
| Swedish | Svenska | Latin | LTR | Caveat | Handwriting |
| Czech | Čeština | Latin | LTR | Caveat | Handwriting |
| Romanian | Română | Latin | LTR | Caveat | Handwriting |
| Hungarian | Magyar | Latin | LTR | Caveat | Handwriting |
| Malay | Bahasa Melayu | Latin | LTR | Caveat | Handwriting |
| Swahili | Kiswahili | Latin | LTR | Caveat | Handwriting |
| Filipino | Filipino | Latin | LTR | Caveat | Handwriting |
| Catalan | Català | Latin | LTR | Caveat | Handwriting |
| Russian | Русский | Cyrillic | LTR | Bad Script | Handwriting |
| Ukrainian | Українська | Cyrillic | LTR | Bad Script | Handwriting |
| Bulgarian | Български | Cyrillic | LTR | Bad Script | Handwriting |
| Serbian | Српски | Cyrillic | LTR | Bad Script | Handwriting |
| Arabic | العربية | Arabic | RTL | Aref Ruqaa Ink | Handwriting |
| Persian | فارسی | Arabic | RTL | Aref Ruqaa Ink | Handwriting |
| Urdu | اردو | Arabic | RTL | Gulzar | Handwriting |
| Punjabi (Shahmukhi) | پنجابی | Arabic | RTL | Gulzar | Handwriting |
| Pashto | پښتو | Arabic | RTL | Lateef | Text face |
| Sindhi | سنڌي | Arabic | RTL | Lateef | Text face |
| Hindi | हिन्दी | Devanagari | LTR | Kalam | Handwriting |
| Marathi | मराठी | Devanagari | LTR | Kalam | Handwriting |
| Nepali | नेपाली | Devanagari | LTR | Kalam | Handwriting |
| Sanskrit | संस्कृतम् | Devanagari | LTR | Kalam | Handwriting |
| Punjabi (Gurmukhi) | ਪੰਜਾਬੀ | Gurmukhi | LTR | Mukta Mahee | Text face |
| Bengali | বাংলা | Bengali | LTR | Galada | Handwriting |
| Tamil | தமிழ் | Tamil | LTR | Kavivanar | Handwriting |
| Telugu | తెలుగు | Telugu | LTR | Akaya Telivigala | Handwriting |
| Gujarati | ગુજરાતી | Gujarati | LTR | Mukta Vaani | Text face |
| Thai | ไทย | Thai | LTR | Sriracha | Handwriting |
| Chinese (Simplified) | 简体中文 | Chinese | LTR | ZCOOL KuaiLe | Handwriting |
| Japanese | 日本語 | Japanese | LTR | Klee One | Handwriting |
| Korean | 한국어 | Korean | LTR | Nanum Pen Script | Handwriting |

Pashto and Sindhi use Lateef, a Naskh text face, because no open handwriting font we could ship covers their letters. Gurmukhi uses Mukta Mahee and Gujarati uses Mukta Vaani for the same reason. Urdu and Shahmukhi use Gulzar, which is Nastaliq, the hand those languages are actually written in.

A test renders every script family, and the suite fails if a language sample shapes to a missing glyph. Thai wraps on grapheme clusters so vowel marks stay with their consonants. Dictionary line-breaking for Thai is still to come.

More sample pages: [Hindi](samples/hindi-single-ruled.png), [Arabic](samples/arabic-single-ruled.png), [Japanese](samples/japanese-square-grid.png), [Korean](samples/korean-square-grid.png).

## Quick start on a Mac

These commands are the same on Linux. Use Python 3.11+ and Node 20+.

```bash
git clone https://github.com/codexmaham/qalam.git
cd qalam

cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Voice also needs ffmpeg: brew install ffmpeg
python3 -m uvicorn qalam.main:app --host 127.0.0.1 --port 8000
```

Second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173.

If the page says the renderer is not running, the first terminal is the one to check. The API is only on your machine, at http://127.0.0.1:8000.

```bash
cd backend && source .venv/bin/activate && pytest
```

The Python packages publish macOS arm64 wheels (`uharfbuzz`, `freetype-py`, `Pillow`). You do not need Xcode for a normal install, and you do not need a GPU. A page is a CPU render and comes back in well under a second.

## How it is built

The browser is a small React app. The renderer is a Python service, so local speech-to-text and HarfBuzz shaping sit next to each other.

```mermaid
flowchart LR
  notes[Notes page] --> api[FastAPI]
  voice[Voice page] --> api
  api --> renderer[HandwritingRenderer]
  renderer --> fonts[Bundled fonts]
  renderer --> clone[Photo contours]
  renderer --> photo[Your page photo]
  fonts --> pdf[A4 PDF and PNG]
  clone --> pdf
  photo --> pdf
```

Text is split into words, or into grapheme clusters for Chinese, Japanese, Korean, and Thai. Each piece is shaped, then jittered in a way that script can survive: Arabic words stay joined, Indic and Thai marks stay on their bases, and Latin letters move one by one. A sample style reuses that path for any character it could not cut out of the photo. The same function draws the preview, the PNG, and the PDF.

Fonts are stored in the repo under the SIL Open Font License so the app works with no network. Copyright lines are in [backend/fonts/NOTICE.md](backend/fonts/NOTICE.md).

## Roadmap

- A one-shot handwriting model behind the same renderer interface, so a single sample can synthesise strokes instead of cutting contours out of a photo. The contour composer is the stand-in that model would replace.
- A stroke-synthesis engine for the bundled faces, so the writing varies like a hand instead of a font.
- More paper: dotted tracing, graph, Urdu copy lines, and a worksheet header.
- Vertical genkō yōshi.
- Dictionary line-breaking for Thai.
- Handwriting faces for the scripts that are still on a text face.
- A PDF you can select and copy, not only print.

## Contributing

Adding a language is a font file plus a block in `backend/languages.toml`. The steps, including which jitter profile to pick, are in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

The application code is [MIT](LICENSE). The fonts stay under the [SIL Open Font License 1.1](backend/fonts/OFL.txt).
