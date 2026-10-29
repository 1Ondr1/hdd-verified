"""Машинный перевод комментариев к отчётам через DeepL.

Перевод не автоматический: пользователь нажимает «Перевести», результат
сохраняется в базе и больше не запрашивается. Без ключа ``DEEPL_API_KEY``
сервис считает себя недоступным, и кнопка в интерфейсе не показывается.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

from games.i18n import current_language

FREE_URL = "https://api-free.deepl.com/v2/translate"
PRO_URL = "https://api.deepl.com/v2/translate"

#: Код языка сайта → код языка DeepL.
_TARGETS = {"ru": "RU", "en": "EN", "uk": "UK"}


class TranslationError(Exception):
    """DeepL недоступен, отклонил ключ или не смог перевести текст."""


def available() -> bool:
    """Есть ли ключ DeepL: без него кнопку перевода не показываем."""
    return bool(settings.DEEPL_API_KEY)


def target_language(language: str | None = None) -> str:
    """Код языка DeepL для активного языка сайта."""
    return _TARGETS.get(language or current_language(), "EN")


def _endpoint() -> str:
    """Бесплатные ключи DeepL заканчиваются на «:fx» и ходят на свой адрес."""
    return FREE_URL if settings.DEEPL_API_KEY.endswith(":fx") else PRO_URL


def translate(text: str, language: str | None = None) -> str:
    """Перевести текст на язык интерфейса. Бросает ``TranslationError``."""
    text = (text or "").strip()
    if not text:
        return ""
    if not available():
        raise TranslationError("Ключ DeepL не настроен")

    body = urllib.parse.urlencode(
        {"text": text, "target_lang": target_language(language)}
    ).encode()
    request = urllib.request.Request(
        _endpoint(),
        data=body,
        method="POST",
        headers={
            "Authorization": f"DeepL-Auth-Key {settings.DEEPL_API_KEY}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "HDDVerified/0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.DEEPL_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as exc:
        raise TranslationError(f"DeepL ответил ошибкой {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise TranslationError(f"Не удалось связаться с DeepL: {exc}") from exc

    translations = data.get("translations") or []
    result = translations[0].get("text", "") if translations else ""
    if not result:
        raise TranslationError("DeepL вернул пустой перевод")
    return result
