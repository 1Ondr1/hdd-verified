"""Поиск по магазинам: Steam в приоритете, Epic Games — дополнение.

Steam — основной источник, потому что у него есть требования к диску.
Epic нужен для игр, которых в Steam нет. Одинаковые игры из двух магазинов
не показываем дважды: при совпадении названий остаётся Steam.
"""

from __future__ import annotations

from games.services import epic, steam
from games.services.catalog import SearchResult, normalize_title


class SearchError(Exception):
    """Ни один магазин не ответил."""


def search_games(term: str, limit: int = 20) -> list[SearchResult]:
    """Найти игры в Steam и Epic, убрав дубли между магазинами."""
    term = (term or "").strip()
    if len(term) < 2:
        return []

    results: list[SearchResult] = []
    errors: list[str] = []

    for loader in (steam.search_games, epic.search_games):
        try:
            results.extend(loader(term, limit=limit))
        except (steam.SteamError, epic.EpicError) as exc:
            errors.append(str(exc))

    if not results and errors:
        raise SearchError("; ".join(errors))

    return _rank(_dedupe(results), term)[:limit]


def _dedupe(results: list[SearchResult]) -> list[SearchResult]:
    """Оставить первое вхождение каждой игры.

    Steam идёт первым, поэтому при совпадении названий с Epic побеждает он.
    """
    seen: set[str] = set()
    unique: list[SearchResult] = []
    for item in results:
        key = normalize_title(item.name)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        unique.append(item)
    return unique


def _rank(results: list[SearchResult], term: str) -> list[SearchResult]:
    """Поднять точные совпадения над нерелевантной выдачей Steam.

    Steam иногда находит «хоть что-нибудь» (по запросу Fortnite — тренажёры
    прицеливания), и без этого Epic-эксклюзив терялся бы в конце списка.
    При равной релевантности Steam остаётся выше: сортировка стабильная.
    """
    query = normalize_title(term)

    def relevance(item: SearchResult) -> int:
        name = normalize_title(item.name)
        if not query:
            return 0
        if name == query:
            return 2
        return 1 if name.startswith(query) else 0

    return sorted(results, key=relevance, reverse=True)
