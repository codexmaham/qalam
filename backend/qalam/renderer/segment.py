"""Split text into shapeable units.

Words stay whole so Arabic joining and Indic conjuncts are not broken.
CJK, Kana, Hangul, and Thai break on grapheme clusters, which is what
a notebook grid and a line-breaker both need. Thai has no spaces between
words; cluster breaks keep marks on their bases. Dictionary wrapping can
replace this later without changing the renderer interface.
"""

from __future__ import annotations

import unicodedata

import regex

_GRAPHEME = regex.compile(r"\X")

# Scripts that wrap (and sit in a grid cell) one cluster at a time.
CLUSTER_SCRIPTS = {"Hani", "Hira", "Kana", "Hang", "Thai"}
JOINING_SCRIPTS = {"Arab"}


def script_of(ch: str) -> str:
    """Rough Unicode-block script tag. Marks inherit from their base."""

    o = ord(ch)
    if o < 128:
        return "Latn" if ch.isalpha() else "Zyyy"
    if 0x00C0 <= o <= 0x024F or 0x1E00 <= o <= 0x1EFF:
        return "Latn"
    if 0x0400 <= o <= 0x052F:
        return "Cyrl"
    if (
        0x0600 <= o <= 0x06FF
        or 0x0750 <= o <= 0x077F
        or 0x08A0 <= o <= 0x08FF
        or 0xFB50 <= o <= 0xFDFF
        or 0xFE70 <= o <= 0xFEFF
    ):
        return "Arab"
    if 0x0900 <= o <= 0x097F:
        return "Deva"
    if 0x0980 <= o <= 0x09FF:
        return "Beng"
    if 0x0A00 <= o <= 0x0A7F:
        return "Guru"
    if 0x0A80 <= o <= 0x0AFF:
        return "Gujr"
    if 0x0B80 <= o <= 0x0BFF:
        return "Taml"
    if 0x0C00 <= o <= 0x0C7F:
        return "Telu"
    if 0x0E00 <= o <= 0x0E7F:
        return "Thai"
    if 0x3040 <= o <= 0x309F:
        return "Hira"
    if 0x30A0 <= o <= 0x30FF or 0x31F0 <= o <= 0x31FF:
        return "Kana"
    if 0xAC00 <= o <= 0xD7AF or 0x1100 <= o <= 0x11FF or 0x3130 <= o <= 0x318F:
        return "Hang"
    if (
        0x4E00 <= o <= 0x9FFF
        or 0x3400 <= o <= 0x4DBF
        or 0xF900 <= o <= 0xFAFF
        or 0x3000 <= o <= 0x303F
        or 0xFF00 <= o <= 0xFFEF
    ):
        return "Hani"
    category = unicodedata.category(ch)
    if category.startswith("M") or category == "Cf":
        return "Zinh"
    return "Zyyy"


def dominant_script(text: str) -> str:
    for ch in text:
        script = script_of(ch)
        if script not in {"Zyyy", "Zinh"}:
            return script
    return "Zyyy"


def _grapheme_end(text: str, index: int) -> int:
    match = _GRAPHEME.match(text, index)
    return match.end() if match else index + 1


def segment(text: str) -> list[str]:
    """Return shapeable chunks, with `\\n` preserved as its own unit."""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    units: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        ch = text[index]
        if ch == "\n":
            units.append("\n")
            index += 1
            continue
        if ch.isspace():
            end = index + 1
            while end < length and text[end].isspace() and text[end] != "\n":
                end += 1
            units.append(text[index:end])
            index = end
            continue
        script = script_of(ch)
        if script in CLUSTER_SCRIPTS:
            end = _grapheme_end(text, index)
            units.append(text[index:end])
            index = end
            continue
        end = index + 1
        while end < length:
            nxt = text[end]
            if nxt.isspace():
                break
            nxt_script = script_of(nxt)
            if nxt_script in CLUSTER_SCRIPTS:
                break
            if nxt_script not in {script, "Zyyy", "Zinh"} and script not in {"Zyyy", "Zinh"}:
                break
            if script in {"Zyyy", "Zinh"} and nxt_script not in {"Zyyy", "Zinh"}:
                script = nxt_script
            end += 1
        units.append(text[index:end])
        index = end
    return units
