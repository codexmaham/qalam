# Security

Qalam runs on your computer. The page, a photo of your notebook, a recording, and an uploaded handwriting sample stay there. The only download is the Whisper model, the first time you transcribe, into `~/.cache/qalam/whisper`.

## Reporting a vulnerability

Use [private vulnerability reporting](https://github.com/codexmaham/qalam/security/advisories/new) on this repository. Do not open a public issue for a security report, and do not attach a child's handwriting or a recording.

Include the version or commit, the command you ran, and what you expected to happen.

## In scope

The local API, the handwriting renderer, and the page the API serves. A public demo (`docker compose up`) is the same program: do not upload handwriting you cannot share.
