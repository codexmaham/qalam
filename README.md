<p align="center">
  <img src="docs/assets/logo.svg" alt="Qalam" width="320">
</p>

<p align="center">
  <strong>Speak it. See it handwritten. Print it.</strong>
</p>

<p align="center">
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-blue"></a>
  <a href="https://github.com/codexmaham/qalam/actions/workflows/ci.yml"><img alt="CI status" src="https://img.shields.io/github/actions/workflow/status/codexmaham/qalam/ci.yml?branch=main&amp;label=CI"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11+-3776AB?logo=python&amp;logoColor=white">
  <img alt="React 19" src="https://img.shields.io/badge/react-19-149ECA?logo=react&amp;logoColor=white">
  <a href="CONTRIBUTING.md"><img alt="PRs welcome" src="https://img.shields.io/badge/PRs-welcome-brightgreen"></a>
  <a href="https://github.com/codexmaham/qalam/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/codexmaham/qalam?style=flat&amp;label=stars"></a>
</p>

<p align="center">
  <img src="docs/demo/qalam-demo.gif" alt="Qalam demo: type a lesson, switch language, speak it, and print it" width="720">
</p>

<p align="center">
  <img src="docs/demo/notes-urdu.png" alt="Urdu homework, written right to left" width="340">
  <img src="docs/demo/voice-homework.png" alt="A spoken lesson transcribed and written on the page" width="340">
</p>

<!--
Full demo video (MP4). It is not stored in this repository.
Upload the file with GitHub's editor, then replace this comment with the attachment:

![Qalam demo](https://github.com/user-attachments/assets/REPLACE_ME)
-->

## Why Qalam

A lesson should look like a notebook page. Qalam runs on the school computer: you type or you speak, and the page on screen is the page you print. Nothing is uploaded. An 8 GB MacBook Air is enough.

| | |
| --- | --- |
| **Voice to homework** | Record or upload audio. Whisper transcribes on this computer, and the notebook writes the page. |
| **Your own handwriting** | Upload a sample, or the printed template sheet. That hand becomes the default. |
| **Write on your page** | Photograph a notebook. Qalam finds the rules and writes on the empty lines. |
| **42 languages** | Latin, right-to-left Arabic and Urdu, Devanagari, and Chinese, Japanese, and Korean. Shaped with HarfBuzz, not drawn character by character. |
| **Practice and worksheets** | Dotted letters and words, graph paper, and a sheet with name, date, and class. |
| **PDF export** | Download the page as A4 or US Letter PDF, or as a PNG. |
| **Fully offline** | Fonts ship in the repo. An 8 GB M1 runs the renderer and Whisper. The only download is the Whisper model, once. |

## Quick start

**macOS.** Python, ffmpeg, and Node come from Homebrew.

```bash
git clone https://github.com/codexmaham/qalam.git
cd qalam
./scripts/setup-macos.sh
cd backend
source .venv/bin/activate
python3 -m uvicorn qalam.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000.

On Linux, use Python 3.11+, Node 20+, and ffmpeg, then the same `venv` and `npm` steps. Details are in [CONTRIBUTING.md](CONTRIBUTING.md).

**Docker**

```bash
docker compose up --build
```

The container listens on port 8000. Saved handwriting and the Whisper download stay in two volumes.

## Languages

42 languages. **Handwriting** is an open pen, brush, or handwriting face. **Text face** means no open handwriting font covers that script, so the page says so and uses a text face.

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

Urdu and Shahmukhi are set in Gulzar (Nastaliq). Pashto, Sindhi, Gurmukhi, and Gujarati use a text face because no open handwriting font we could ship covers their letters. Add a language with a font file plus a block in `backend/languages.toml`. The steps are in [CONTRIBUTING.md](CONTRIBUTING.md).

## Gallery

<table>
  <tr>
    <td align="center"><img src="samples/english-four-line.png" alt="English on four-line copy" width="200"><br>English</td>
    <td align="center"><img src="samples/urdu-single-ruled.png" alt="Urdu in Nastaliq on ruled paper" width="200"><br>Urdu</td>
    <td align="center"><img src="samples/chinese-tianzige.png" alt="Simplified Chinese on tianzige" width="200"><br>Chinese</td>
    <td align="center"><img src="samples/hindi-single-ruled.png" alt="Hindi on single-ruled paper" width="200"><br>Hindi</td>
  </tr>
  <tr>
    <td align="center"><img src="samples/school-neat.png" alt="Neat school notes" width="200"><br>Neat school notes</td>
    <td align="center"><img src="samples/from-your-hand.png" alt="A sentence set from a handwriting sheet" width="200"><br>Your hand</td>
    <td align="center"><img src="samples/on-your-page.png" alt="Handwriting placed on a photographed page" width="200"><br>Your page</td>
    <td align="center"><img src="samples/worksheet.png" alt="A worksheet with a heading and bullets" width="200"><br>Worksheet</td>
  </tr>
  <tr>
    <td align="center"><img src="samples/practice-english.png" alt="English letters to trace" width="200"><br>Practice</td>
    <td align="center"><img src="samples/practice-urdu.png" alt="Urdu words on copy lines" width="200"><br>Urdu practice</td>
    <td align="center"><img src="samples/japanese-square-grid.png" alt="Japanese on a square grid" width="200"><br>Japanese</td>
    <td align="center"><img src="samples/korean-square-grid.png" alt="Korean on a square grid" width="200"><br>Korean</td>
  </tr>
</table>

More pages live in [`samples/`](samples/), including Arabic, graph paper, stroke hand, and the practice grids for Chinese, Japanese, and Korean.

## How it works

The browser is a small React app. A Python service on the same machine shapes the text, draws the page, and runs Whisper.

```mermaid
flowchart LR
  notes[Notes page] --> api[FastAPI]
  voice[Voice page] --> api
  api --> renderer[HandwritingRenderer]
  renderer --> fonts[Bundled fonts]
  renderer --> strokes[Graves stroke model]
  renderer --> clone[Photo contours]
  renderer --> photo[Your page photo]
  fonts --> pdf[PDF and PNG]
  strokes --> pdf
  clone --> pdf
  photo --> pdf
```

Arabic words stay joined. Indic and Thai marks stay on their bases. Latin letters move one by one. The same function draws the preview, the PNG, and the PDF.

## Roadmap

Shipped: practice sheets, graph and worksheet paper, A4 and Letter, margins, pen thickness, homework markup, the Graves stroke style for Latin, a saved handwriting default, local Whisper, and Docker.

Still open:

- Vertical genkō yōshi. This version is horizontal, with a centre gutter.
- A stroke model for scripts other than Latin.
- A one-shot model that can invent a joined hand from one photo.
- Dictionary line-breaking for Thai.
- Handwriting faces for the scripts that are still on a text face.
- A PDF you can select and copy, not only print.

## Contributing

A new language is a font file plus a block in `backend/languages.toml`. Setup, tests, and the jitter profiles are in [CONTRIBUTING.md](CONTRIBUTING.md). Smaller tasks are listed in [docs/good-first-issues.md](docs/good-first-issues.md).

Security reports go through [SECURITY.md](SECURITY.md). Please do not file those as public issues.

## License

The code is [MIT](LICENSE), copyright Syeda Maham Fatima. The fonts stay under the [SIL Open Font License 1.1](backend/fonts/OFL.txt).

<p align="center">
  <strong>If Qalam is useful, <a href="https://github.com/codexmaham/qalam">star it</a>.</strong>
</p>
