"""Разбор требований магазинов к накопителю.

Steam отдаёт требования куском HTML, Epic — списком пунктов. И там, и там
нужно вытащить объём на диске и упоминание SSD, поэтому разбор общий:
на вход идёт текст, на выход — число гигабайт и признак SSD.
"""

from __future__ import annotations

import html
import re

_TAG_RE = re.compile(r"<[^>]+>")
_LINE_BREAK_RE = re.compile(r"</li>|<br\s*/?>|</p>", re.I)

#: Число с единицей объёма; между ними может стоять короткое слово
#: вроде «SSD» (Steam иногда отдаёт «60 SSD GB»).
_STORAGE_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:[A-ZА-Я]{2,6}\s+)?(gb|гб|mb|мб|tb|тб)\b", re.I
)
_UNIT_TO_GB = {
    "gb": 1.0,
    "гб": 1.0,
    "tb": 1000.0,
    "тб": 1000.0,
    "mb": 0.001,
    "мб": 0.001,
}

#: Строки про оперативную память не имеют отношения к диску.
_RAM_KEYWORDS = ("озу", "оперативн", "memory", " ram")
#: Признаки строки с требованием к накопителю.
_STORAGE_KEYWORDS = (
    "место на диске",
    "дискового пространства",
    "свободного места",
    "storage",
    "hard disk",
    "disk space",
)


def storage_gb(requirement_text: str) -> float | None:
    """Объём из требований к накопителю.

    Сначала смотрим строки про диск, и только если таких нет — берём
    максимум по остальным, кроме оперативной памяти.
    """
    preferred: list[float] = []
    fallback: list[float] = []

    for line in _requirement_lines(requirement_text):
        lowered = line.lower()
        if any(keyword in lowered for keyword in _RAM_KEYWORDS):
            continue
        is_storage_line = any(keyword in lowered for keyword in _STORAGE_KEYWORDS)
        for value, unit in _STORAGE_RE.findall(line):
            size = float(value.replace(",", ".")) * _UNIT_TO_GB[unit.lower()]
            (preferred if is_storage_line else fallback).append(size)

    sizes = preferred or fallback
    return round(max(sizes), 1) if sizes else None


def requires_ssd(requirement_text: str) -> bool | None:
    """``True``, если SSD упомянут; ``None``, если требований нет вовсе."""
    text = _plain_text(requirement_text).lower()
    if not text.strip():
        return None
    return "ssd" in text or "твердотельн" in text


def _requirement_lines(markup: str) -> list[str]:
    """Разбить HTML требований на отдельные пункты."""
    text = _LINE_BREAK_RE.sub("\n", markup or "")
    text = html.unescape(_TAG_RE.sub(" ", text))
    return [" ".join(line.split()) for line in text.splitlines() if line.strip()]


def _plain_text(markup: str) -> str:
    return html.unescape(_TAG_RE.sub(" ", markup or ""))
