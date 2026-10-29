"""Клиент публичного GraphQL Epic Games Store.

Epic не даёт REST-поиска без ключа, зато storefront-запросы GraphQL открыты:
``searchStore`` ищет игры, ``catalogOffer`` отдаёт карточку. Названия берём
в двух локалях, чтобы в базе были и русское, и английское.
"""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache

from games.i18n import current_language
from games.services.catalog import SearchResult, normalize_title
from games.services.requirements import requires_ssd, storage_gb

GRAPHQL_URL = "https://store.epicgames.com/graphql"
CONTENT_URL = "https://store-content.ak.epicgames.com/api/en-US/content/products/{slug}"
REQUEST_TIMEOUT = 20

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}

#: ``category: "games"`` отсекает DLC, наборы валюты и саундтреки.
SEARCH_QUERY = """
query searchStoreQuery(
  $keywords: String!, $country: String!, $locale: String!,
  $count: Int, $category: String
) {
  Catalog {
    searchStore(
      keywords: $keywords, country: $country, locale: $locale,
      count: $count, category: $category
    ) {
      elements {
        title
        id
        namespace
        productSlug
        urlSlug
        description
        keyImages { type url }
      }
    }
  }
}
"""

OFFER_QUERY = """
query catalogQuery($namespace: String!, $id: String!, $locale: String!) {
  Catalog {
    catalogOffer(namespace: $namespace, id: $id, locale: $locale) {
      title
      description
      releaseDate
      urlSlug
      productSlug
      keyImages { type url }
    }
  }
}
"""

_TAG_RE = re.compile(r"<[^>]+>")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_EXTERNAL_ID_RE = re.compile(r"^[A-Za-z0-9_-]+:[A-Za-z0-9_-]+$")

#: Типы изображений от широкой обложки к узкой — первый найденный и берём.
_WIDE_IMAGE_TYPES = (
    "OfferImageWide",
    "DieselStoreFrontWide",
    "OfferImageTall",
    "Thumbnail",
)

#: Для карточек поиска хватает миниатюры: широкая обложка 2560×1440 весит
#: слишком много, когда таких карточек два десятка.
_CARD_IMAGE_TYPES = ("Thumbnail", "OfferImageTall", "OfferImageWide")


#: Признаки пункта с требованием к накопителю в карточке Epic.
_STORAGE_TITLE_WORDS = ("storage", "disk space", "место", "диск", "накопител")


class EpicError(Exception):
    """Epic Store недоступен или вернул неожиданный ответ."""


def current_epic_locale() -> str:
    """Локаль Epic для активного языка сайта.

    Базовая локаль — американская английская, русская запрашивается только
    для русского интерфейса. Украине отдельной локали не нужна: показываем
    английскую версию.
    """
    return "ru" if current_language() == "ru" else settings.EPIC_LOCALE


@dataclass(frozen=True)
class Offer:
    """Карточка предложения в одной локали."""

    title: str
    description: str
    release_date: str
    product_slug: str
    url_slug: str
    images: dict[str, str]


@dataclass(frozen=True)
class Requirements:
    """Требования Epic к накопителю.

    Epic не отдаёт их в GraphQL: нужен отдельный запрос к контентному API
    по слагу товара. Если пункта про диск нет, оба поля остаются пустыми.
    """

    storage_gb: float | None = None
    requires_ssd: bool | None = None


def is_valid_external_id(external_id: str) -> bool:
    return bool(_EXTERNAL_ID_RE.fullmatch(external_id or ""))


def search_games(term: str, limit: int = 10) -> list[SearchResult]:
    """Найти игры Epic Store.

    Базовые названия — английские (регион US), для русского интерфейса
    дополнительно запрашивается русская локаль. Английский поиск делается
    отдельным запросом, потому что GraphQL не умеет отдавать два перевода
    сразу.
    """
    term = (term or "").strip()
    if len(term) < 2:
        return []

    locale = current_epic_locale()
    cache_key = (
        f"epic:search:{settings.EPIC_COUNTRY}:{locale}:"
        f"{urllib.parse.quote(term.casefold(), safe='')}"
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached[:limit]

    count = max(limit, 10)
    elements = _search(term, locale, count)
    english: dict[str, str] = {}
    if locale != "en":
        try:
            english = _titles_by_id(_search(term, "en", count))
        except EpicError:
            # Английские названия — приятный бонус, без них поиск работает.
            english = {}

    results: list[SearchResult] = []
    seen: set[str] = set()
    for element in elements:
        title = element.get("title") or english.get(element.get("id"), "")
        key = normalize_title(title)
        if not key or key in seen:
            continue
        seen.add(key)

        images = _images(element)
        results.append(
            SearchResult(
                source="epic",
                external_id=f"{element['namespace']}:{element['id']}",
                name=title,
                image=next(
                    (images[kind] for kind in _CARD_IMAGE_TYPES if images.get(kind)), ""
                ),
            )
        )

    cache.set(cache_key, results, settings.EPIC_CACHE_TTL)
    return results[:limit]


def game_payload(external_id: str) -> dict:
    """Собрать поля модели ``Game`` по идентификатору Epic.

    Базовая локаль — английская (регион US), русская версия запрашивается
    отдельно для русского интерфейса.
    """
    namespace, offer_id = external_id.split(":", 1)
    offer = fetch_offer(namespace, offer_id, settings.EPIC_LOCALE)
    if settings.EPIC_LOCALE == "en":
        english = offer
    else:
        try:
            english = fetch_offer(namespace, offer_id, "en")
        except EpicError:
            english = offer
    try:
        russian = fetch_offer(namespace, offer_id, "ru")
    except EpicError:
        # Русской локали может не быть — тогда покажем английскую.
        russian = offer

    slug = offer.product_slug or offer.url_slug
    url_locale = "ru" if settings.EPIC_LOCALE == "ru" else "en-US"
    store_url = f"https://store.epicgames.com/{url_locale}/p/{slug}" if slug else ""
    requirements = fetch_requirements(slug)
    return {
        "source": "epic",
        "external_id": external_id,
        "title": offer.title,
        "title_en": english.title,
        "title_ru": russian.title,
        "genre": "",
        "genre_en": "",
        "genre_ru": "",
        "release_year": _release_year(offer.release_date),
        "cover_url": next(
            (offer.images[kind] for kind in _WIDE_IMAGE_TYPES if offer.images.get(kind)),
            "",
        ),
        "short_description": _plain_text(offer.description),
        "short_description_en": _plain_text(english.description),
        "short_description_ru": _plain_text(russian.description),
        "storage_gb": requirements.storage_gb,
        "requires_ssd": requirements.requires_ssd,
        "store_url": store_url,
    }


def fetch_offer(namespace: str, offer_id: str, locale: str) -> Offer:
    """Запросить карточку предложения в конкретной локали."""
    cache_key = f"epic:offer:{namespace}:{offer_id}:{locale}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    data = _post(OFFER_QUERY, {"namespace": namespace, "id": offer_id, "locale": locale})
    raw = ((data.get("data") or {}).get("Catalog") or {}).get("catalogOffer")
    if not raw:
        raise EpicError(f"Epic не вернул карточку {namespace}:{offer_id}")

    offer = Offer(
        title=(raw.get("title") or "").strip(),
        description=raw.get("description") or "",
        release_date=raw.get("releaseDate") or "",
        product_slug=raw.get("productSlug") or "",
        url_slug=raw.get("urlSlug") or "",
        images=_images(raw),
    )
    cache.set(cache_key, offer, settings.EPIC_CACHE_TTL)
    return offer


def fetch_requirements(slug: str) -> Requirements:
    """Требования к накопителю из контентного API Epic.

    GraphQL их не отдаёт, поэтому запрашиваем страницу товара по слагу.
    Контентный API всегда отвечает по-английски — для разбора это даже
    удобнее. Ошибка или отсутствие слага не должны ломать импорт игры:
    в таком случае просто не показываем требование.
    """
    if not slug:
        return Requirements()

    cache_key = f"epic:requirements:{slug}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        data = _get_json(
            CONTENT_URL.format(slug=urllib.parse.quote(slug, safe=""))
        )
    except EpicError:
        return Requirements()

    requirements = _requirements_from_payload(data)
    cache.set(cache_key, requirements, settings.EPIC_CACHE_TTL)
    return requirements


def _requirements_from_payload(data: dict) -> Requirements:
    """Выбрать из карточки Epic пункт про диск для Windows."""
    for page in data.get("pages") or []:
        systems = ((page.get("data") or {}).get("requirements") or {}).get("systems")
        for system in systems or []:
            if (system.get("systemType") or "").lower() != "windows":
                continue
            for item in system.get("details") or []:
                title = (item.get("title") or "").lower()
                if not any(word in title for word in _STORAGE_TITLE_WORDS):
                    continue
                text = " ".join(
                    str(item.get(key) or "")
                    for key in ("title", "minimum", "recommended")
                )
                size = storage_gb(text)
                if size is not None:
                    return Requirements(
                        storage_gb=size,
                        requires_ssd=requires_ssd(text),
                    )
    return Requirements()


def _search(term: str, locale: str, count: int) -> list[dict]:
    data = _post(
        SEARCH_QUERY,
        {
            "keywords": term,
            "country": settings.EPIC_COUNTRY,
            "locale": locale,
            "count": count,
            "category": "games",
        },
    )
    store = ((data.get("data") or {}).get("Catalog") or {}).get("searchStore")
    if not store:
        raise EpicError("Epic не вернул результаты поиска")
    return store.get("elements") or []


def _titles_by_id(elements: list[dict]) -> dict[str, str]:
    return {
        element["id"]: element.get("title") or ""
        for element in elements
        if element.get("id")
    }


def _images(raw: dict) -> dict[str, str]:
    return {
        image["type"]: image["url"]
        for image in raw.get("keyImages") or []
        if image.get("type") and image.get("url")
    }


def _plain_text(markup: str) -> str:
    return " ".join(html.unescape(_TAG_RE.sub(" ", markup or "")).split())


def _release_year(release_date: str) -> int | None:
    match = _YEAR_RE.search(release_date or "")
    return int(match.group(0)) if match else None


def _get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as exc:
        raise EpicError(f"Epic ответил ошибкой {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise EpicError(f"Не удалось связаться с Epic: {exc}") from exc


def _post(query: str, variables: dict) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
    request = urllib.request.Request(
        GRAPHQL_URL, data=body, headers=HEADERS, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as exc:
        raise EpicError(f"Epic ответил ошибкой {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise EpicError(f"Не удалось связаться с Epic: {exc}") from exc

    if data.get("errors"):
        message = data["errors"][0].get("message", "неизвестная ошибка")
        raise EpicError(f"Epic вернул ошибку: {message}")
    return data
