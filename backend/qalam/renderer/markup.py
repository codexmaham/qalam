"""A small homework markup on top of plain text.

`# Heading` is larger. `- item` is a bullet. A line of `---` is a rule.
`__word__` is underlined. `x^2`, `H_2O`, and `$1/2$` become simple math.
Everything else is ordinary notebook text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SUP = str.maketrans("0123456789+-=()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾")
_SUB = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")
_UNDER = re.compile(r"__([^_\n]+)__")
_SUPER = re.compile(r"\^(\{[^{}\n]+\}|\d+)")
_SUBSC = re.compile(r"_(\{[^{}\n]+\}|\d+)")
_FRAC = re.compile(r"\$(\d+)\s*/\s*(\d+)\$")


@dataclass
class Run:
    text: str
    scale: float = 1.0
    underline: bool = False
    bullet: bool = False
    rule: bool = False


def mathify(text: str) -> str:
    text = _FRAC.sub(lambda match: match.group(1).translate(_SUP) + "⁄" + match.group(2).translate(_SUB), text)

    def scr(table):
        def replace(match: re.Match[str]) -> str:
            body = match.group(1)
            if body.startswith("{") and body.endswith("}"):
                body = body[1:-1]
            return body.translate(table)

        return replace

    text = _SUPER.sub(scr(_SUP), text)
    text = _SUBSC.sub(scr(_SUB), text)
    return text


def parse_line(raw: str) -> list[Run]:
    stripped = raw.strip()
    if not stripped:
        return []
    if re.fullmatch(r"[-*_]{3,}", stripped):
        return [Run("", rule=True)]
    scale = 1.0
    bullet = False
    body = raw.rstrip()
    heading = re.match(r"^\s*#{1,3}\s+(.*)$", body)
    if heading:
        scale = 1.35
        body = heading.group(1)
    else:
        item = re.match(r"^\s*[-*]\s+(.*)$", body)
        if item:
            bullet = True
            body = item.group(1)
    runs: list[Run] = []
    cursor = 0
    for match in _UNDER.finditer(body):
        if match.start() > cursor:
            runs.append(Run(mathify(body[cursor : match.start()]), scale=scale, bullet=bullet and not runs))
        runs.append(Run(mathify(match.group(1)), scale=scale, underline=True, bullet=bullet and not runs))
        cursor = match.end()
    if cursor < len(body):
        runs.append(Run(mathify(body[cursor:]), scale=scale, bullet=bullet and not runs))
    return [run for run in runs if run.text or run.rule]


def split_lines(text: str) -> list[str]:
    lines = text.split("\n")
    if text.endswith("\n") and lines:
        lines = lines[:-1]
    return lines
