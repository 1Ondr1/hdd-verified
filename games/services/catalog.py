"""Общие понятия каталога: результат поиска и сравнение названий.

Магазины возвращают разные идентификаторы: у Steam это AppID, у Epic —
пара ``namespace:id``. Поэтому везде используется пара
``(source, external_id)``, а не числовой ключ.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.urls import reverse

#: Слова, которые описывают издание, а не саму игру. Если они стоят в конце
#: названия, при сравнении их отбрасываем: «Ведьмак 3 — Обновлённое издание»
#: и «Ведьмак 3» — одна игра в двух магазинах.
_EDITION_WORDS = frozenset(
    {
        "edition", "издание", "издания", "версия",
        "remastered", "remaster", "remake",
        "definitive", "complete", "deluxe", "ultimate", "premium",
        "gold", "collector", "enhanced",
        "goty", "game", "of", "the", "year",
        "обновлённое", "обновленное", "полное", "коллекционное", "золотое",
        "делюкс", "ультимативное", "расширенное", "подарочное", "специальное",
        "премиум", "люкс",
    }
)

_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)


@dataclass(frozen=True)
class SearchResult:
    """Строка поиска из любого магазина."""

    source: str
    external_id: str
    name: str
    image: str
    fallback_image: str = ""

    @property
    def url(self) -> str:
        return reverse("game_detail", args=[self.source, self.external_id])


def normalize_title(title: str) -> str:
    """Привести название к виду для сравнения между магазинами.

    Регистр, пунктуация и суффикс издания не должны мешать понять, что
    «The Witcher 3: Wild Hunt — Remastered» и «Ведьмак 3: Дикая Охота»
    в базе — одна и та же игра.
    """
    text = (title or "").casefold().replace("&", " and ")
    words = _PUNCT_RE.sub(" ", text).split()
    while words and words[-1] in _EDITION_WORDS:
        words.pop()
    return " ".join(words)
