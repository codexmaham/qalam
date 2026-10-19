# Qalam

**Speak it. See it handwritten. Print it.**

Qalam (قلم, a pen) turns a lesson into a notebook page. You type or paste the text, pick a language and a paper, and print an A4 PDF. The writing is shaped properly for each script, then nudged a little so it does not look like a font stamped in a straight line.

It runs on the school computer. Nothing is uploaded. A MacBook Air with 8 GB of memory is enough.

This first version is the text path: typed notes, a live page, and a PDF. Voice comes next. Whisper will transcribe on the same machine, and the page you already see will be the page it writes.

![English four-line copy page](samples/english-four-line.png)

## What you can do today

- Type or paste text and watch a notebook page update.
- Choose a language. Right-to-left scripts are set right to left, and complex scripts are shaped with HarfBuzz, not drawn character by character.
- Pick the paper: single-ruled, four-line English copy, tianzige (the Chinese character grid), or an open square grid in the spirit of genkō yōshi and wongoji.
- Pick an ink: ballpoint blue, black, navy, green, red, or pencil.
- Put a name and a date on the sheet.
- Download a multi-page A4 PDF.
- Add a language by adding a font and a block of config. See [CONTRIBUTING.md](CONTRIBUTING.md).

The Voice page is a placeholder. Recording and transcription are the next step, on purpose: the notebook renderer is the part every later feature writes through.

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

The browser is a small React app. The renderer is a Python service, because the next piece is local speech-to-text and because shaping has to be HarfBuzz.

```mermaid
flowchart LR
  notes[Notes page] --> api[FastAPI]
  voice[Voice page, next] --> api
  api --> renderer[HandwritingRenderer]
  renderer --> shape[HarfBuzz]
  renderer --> jitter[Jitter]
  renderer --> paper[Notebook template]
  paper --> pdf[A4 PDF]
```

Text is split into words, or into grapheme clusters for Chinese, Japanese, Korean, and Thai. Each piece is shaped, then jittered in a way that script can survive: Arabic words stay joined, Indic and Thai marks stay on their bases, and Latin letters move one by one. The same function draws the preview and the PDF. A stroke engine can replace that function later without changing the page.

Fonts are stored in the repo under the SIL Open Font License so the app works with no network. Copyright lines are in [backend/fonts/NOTICE.md](backend/fonts/NOTICE.md).

## Roadmap

- Voice, with Whisper through whisper.cpp, on this computer. Audio is not uploaded.
- A stroke-synthesis engine behind the same renderer interface, so the writing varies like a hand instead of a font.
- Cloning a teacher's handwriting from a photograph.
- More paper: dotted tracing, graph, Urdu copy lines, and a worksheet header.
- Vertical genkō yōshi.
- Dictionary line-breaking for Thai.
- Handwriting faces for the scripts that are still on a text face.
- A PDF you can select and copy, not only print.

## Contributing

Adding a language is a font file plus a block in `backend/languages.toml`. The steps, including which jitter profile to pick, are in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

The application code is [MIT](LICENSE). The fonts stay under the [SIL Open Font License 1.1](backend/fonts/OFL.txt).
