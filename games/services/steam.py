"""Клиент публичного Steam Store API: поиск игр и карточка приложения."""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache

from games.i18n import current_language
from games.services.catalog import SearchResult
from games.services.requirements import requires_ssd, storage_gb

REQUEST_TIMEOUT = 20
HEADERS = {
    "User-Agent": "HDDVerified/0.1 (+https://github.com/hdd-verified)",
    "Accept-Language": "en-US,en;q=0.9",
}

SEARCH_URL = "https://store.steampowered.com/search/results/"
APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
STORE_PAGE_URL = "https://store.steampowered.com/app/{appid}/"

#: Обложка 460×215 по AppID: не требует запроса и заметно чётче, чем
#: миниатюра 231×87 из результатов поиска.
HEADER_IMAGE_URL = "https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header{suffix}.jpg"

#: Steam хранит локализованные обложки рядом с обычной: ``header_russian.jpg``.
#: Для английского суффикса нет — это и есть базовая обложка. Украинской
#: версии арта у Steam нет (``header_ukrainian.jpg`` отдаёт 404), поэтому
#: для ``uk`` тоже берём базовую.
_LANGUAGE_NAMES = {"ru": "russian", "en": "english", "uk": "ukrainian"}

_TAG_RE = re.compile(r"<[^>]+>")
_SEARCH_ROW_RE = re.compile(r'<a\b[^>]*data-ds-appid="(\d+)"[^>]*>(.*?)</a>', re.S)
_SEARCH_TITLE_RE = re.compile(r'<span class="title">(.*?)</span>', re.S)
_SEARCH_CAPSULE_RE = re.compile(r'<div class="search_capsule">\s*<img src="([^"]+)"')
#: Обложка 616×353 на странице магазина лежит по хешированному адресу,
#: который меняется вместе с артом. Угадать путь нельзя, поэтому читаем его
#: из самой страницы.
_CAPSULE_RE = re.compile(
    r"https://[^\"']*?/steam/apps/(?P<appid>\d+)/[^\"']*?/capsule_616x353[^\"']*?\.jpg(?:\?t=\d+)?"
)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


class SteamError(Exception):
    """Steam API недоступен или вернул неожиданный ответ."""


def search_games(term: str, limit: int = 10) -> list[SearchResult]:
    """Найти игры в Steam Store.

    Используется HTML-выдача с ``category1=998`` («только игры»): она
    отсекает DLC, саундтреки, демо и софт, чего не умеет JSON-поиск.
    """
    term = (term or "").strip()
    if len(term) < 2:
        return []

    language = current_steam_language()
    cache_key = (
        f"steam:search:{language}:{settings.STEAM_COUNTRY}:"
        f"{urllib.parse.quote(term.lower(), safe='')}"
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached[:limit]

    query = urllib.parse.urlencode(
        {
            "term": term,
            "json": 1,
            "infinite": 1,
            "category1": 998,
            "l": language,
            "cc": settings.STEAM_COUNTRY,
        }
    )
    data = _get_json(f"{SEARCH_URL}?{query}")
    if not data.get("success"):
        raise SteamError("Steam не вернул результаты поиска")

    results = _parse_search_rows(data.get("results_html", ""), language)
    cache.set(cache_key, results, settings.STEAM_CACHE_TTL)
    return results[:limit]


def current_steam_language() -> str:
    """Название языка Steam для активной локали сайта."""
    return _LANGUAGE_NAMES.get(current_language(), "english")


def _language_suffix(language: str | None) -> str:
    """Суффикс локализованной обложки: ``_russian`` или пусто."""
    key = (language or current_language()).lower()
    name = _LANGUAGE_NAMES.get(key, key if key in ("russian", "english") else "")
    if name in ("", "english", "ukrainian"):
        return ""
    return f"_{name}"


def header_image(appid: int, language: str | None = None) -> str:
    """Построить адрес обложки-заголовка 460×215 по AppID.

    ``language`` принимает код сайта (``ru``/``en``/``uk``) или имя Steam
    (``russian``/``english``/``ukrainian``). Неизвестный язык даёт базовую
    обложку.
    """
    return HEADER_IMAGE_URL.format(appid=appid, suffix=_language_suffix(language))


def store_capsule(appid: int, language: str = "english") -> str:
    """Широкая обложка 616×353 — ровно та, что показывает страница магазина.

    Steam отдаёт обложки по хешированным адресам вида
    ``shared.akamai.../steam/apps/<id>/<hash>/capsule_616x353_alt_assets_9.jpg``.
    Старые простые пути ``/steam/apps/<id>/capsule_616x353.jpg`` ещё живы,
    но у части игр ведут на устаревший арт (у CS2 — на обложку CS:GO),
    а у части просто отсутствуют. Поэтому адрес берём со страницы магазина
    на нужном языке.

    Возвращает пустую строку, если страница недоступна или обложки нет.
    """
    cache_key = f"steam:capsule:{language}:{appid}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    url = STORE_PAGE_URL.format(appid=appid)
    query = urllib.parse.urlencode({"l": language})
    try:
        markup = _get_html(f"{url}?{query}")
    except SteamError:
        return ""

    capsule = ""
    for match in _CAPSULE_RE.finditer(markup):
        if int(match.group("appid")) == appid:
            capsule = html.unescape(match.group(0))
            break

    cache.set(cache_key, capsule, settings.STEAM_CACHE_TTL)
    return capsule


def _parse_search_rows(markup: str, language: str = "english") -> list[SearchResult]:
    """Разобрать HTML выдачи Steam в список результатов."""
    results: list[SearchResult] = []
    seen: set[int] = set()

    for raw_appid, block in _SEARCH_ROW_RE.findall(markup):
        appid = int(raw_appid)
        title = _SEARCH_TITLE_RE.search(block)
        if appid in seen or title is None:
            continue
        seen.add(appid)

        capsule = _SEARCH_CAPSULE_RE.search(block)
        fallback = html.unescape(capsule.group(1)) if capsule else ""
        results.append(
            SearchResult(
                source="steam",
                external_id=str(appid),
                name=html.unescape(_TAG_RE.sub("", title.group(1))).strip(),
                image=header_image(appid, language),
                fallback_image=fallback or header_image(appid, "en"),
            )
        )
    return results


def fetch_app_details(appid: int, language: str | None = None) -> dict:
    """Запросить карточку приложения у Steam.

    ``language`` позволяет отдельно получить английское название, не меняя
    основной язык интерфейса.
    """
    language = language or settings.STEAM_LANGUAGE
    cache_key = f"steam:appdetails:{language}:{appid}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    query = urllib.parse.urlencode(
        {"appids": appid, "l": language, "cc": settings.STEAM_COUNTRY}
    )
    data = _get_json(f"{APPDETAILS_URL}?{query}")
    entry = data.get(str(appid)) or {}
    if not entry.get("success"):
        raise SteamError(f"Steam не вернул данные для AppID {appid}")

    details = entry["data"]
    cache.set(cache_key, details, settings.STEAM_CACHE_TTL)
    return details


def game_payload(external_id: str) -> dict:
    """Собрать поля модели ``Game`` по Steam AppID.

    Базовая локаль — английская (стандарт региона US), русская и украинская
    версии запрашиваются отдельно: они нужны переключателю языка.
    """
    appid = int(external_id)
    details = fetch_app_details(appid, language=settings.STEAM_LANGUAGE)
    try:
        english_details = (
            details
            if settings.STEAM_LANGUAGE == "english"
            else fetch_app_details(appid, language="english")
        )
    except SteamError:
        # Без английской версии карточка всё равно пригодна.
        english_details = {}
    try:
        russian_details = fetch_app_details(appid, language="russian")
    except SteamError:
        # Русской локализации может не быть — тогда покажем английскую.
        russian_details = {}
    try:
        ukrainian_details = fetch_app_details(appid, language="ukrainian")
    except SteamError:
        # Украинской локализации может не быть — тогда покажем английскую.
        ukrainian_details = {}
    payload = payload_from_details(
        details,
        appid,
        english_name=english_details.get("name") or "",
        english_details=english_details,
        russian_details=russian_details,
        ukrainian_details=ukrainian_details,
    )
    # Обложку берём со страницы магазина: это актуальный арт на нужном
    # языке, а не угаданный адрес в старом формате CDN.
    payload["cover_url"] = store_capsule(appid, "english") or payload["cover_url"]
    payload["cover_url_ru"] = store_capsule(appid, "russian")
    payload["cover_url_uk"] = store_capsule(appid, "ukrainian")
    return payload


def payload_from_details(
    details: dict,
    appid: int,
    english_name: str = "",
    english_details: dict | None = None,
    russian_details: dict | None = None,
    ukrainian_details: dict | None = None,
) -> dict:
    """Превратить ответ Steam в поля модели ``Game``."""
    requirements = details.get("pc_requirements") or {}
    requirement_text = " ".join(
        str(requirements.get(key) or "") for key in ("minimum", "recommended")
    )
    english_details = english_details or {}
    russian_details = russian_details or {}
    ukrainian_details = ukrainian_details or {}
    title = details.get("name") or f"App {appid}"

    return {
        "source": "steam",
        "external_id": str(appid),
        "title": title,
        "title_en": english_name,
        "title_ru": russian_details.get("name") or "",
        "title_uk": ukrainian_details.get("name") or "",
        "genre": ", ".join(genre["description"] for genre in details.get("genres", [])),
        "genre_en": ", ".join(
            genre["description"] for genre in english_details.get("genres", [])
        ),
        "genre_ru": ", ".join(
            genre["description"] for genre in russian_details.get("genres", [])
        ),
        "genre_uk": ", ".join(
            genre["description"] for genre in ukrainian_details.get("genres", [])
        ),
        "release_year": _release_year(details.get("release_date", {})),
        # Запасная обложка: широкий арт со страницы магазина подгружается
        # отдельно (см. ``store_capsule``), а этот адрес остаётся на случай,
        # если страница недоступна.
        "cover_url": details.get("header_image") or header_image(appid, "en"),
        "short_description": details.get("short_description", ""),
        "short_description_en": english_details.get("short_description", ""),
        "short_description_ru": russian_details.get("short_description", ""),
        "short_description_uk": ukrainian_details.get("short_description", ""),
        "storage_gb": storage_gb(requirement_text),
        "requires_ssd": requires_ssd(requirement_text),
        "store_url": f"https://store.steampowered.com/app/{appid}/",
    }


def _get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as exc:
        raise SteamError(f"Steam ответил ошибкой {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SteamError(f"Не удалось связаться со Steam: {exc}") from exc


def _get_html(url: str) -> str:
    request = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return response.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as exc:
        raise SteamError(f"Steam ответил ошибкой {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SteamError(f"Не удалось связаться со Steam: {exc}") from exc


def _plain_text(markup: str) -> str:
    return html.unescape(_TAG_RE.sub(" ", markup or ""))


def _release_year(release_date: dict) -> int | None:
    match = _YEAR_RE.search(str(release_date.get("date") or ""))
    return int(match.group(0)) if match else None

