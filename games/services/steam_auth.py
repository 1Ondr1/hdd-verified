"""Вход через Steam OpenID 2.0.

Паролей на сайте нет: пользователь подтверждает личность на странице
Steam, а сайт получает только публичный SteamID64. Ник и аватар
подтягиваются через Steam Web API, если задан ``STEAM_API_KEY``; без
ключа вход работает, но в интерфейсе остаётся техническое имя
``steam_<id>``.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

OPENID_ENDPOINT = "https://steamcommunity.com/openid/login"
PLAYER_SUMMARIES_URL = (
    "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
)
STEAM_ID_RE = re.compile(r"^https://steamcommunity\.com/openid/id/(\d{17})$")
REQUEST_TIMEOUT = 15
USER_AGENT = "HDDVerified/0.1"


class SteamAuthError(Exception):
    """Steam не подтвердил вход или ответил некорректно."""


def build_login_url(return_to: str, realm: str) -> str:
    """Собрать адрес страницы Steam, которая подтвердит вход.

    ``return_to`` — полный адрес callback-представления, ``realm`` — корень
    сайта (схема и хост). Steam вернёт браузер туда же с подписанным
    ответом OpenID.
    """
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": return_to,
        "openid.realm": realm,
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
    }
    return f"{OPENID_ENDPOINT}?{urllib.parse.urlencode(params)}"


def verify_response(params, expected_return_to: str) -> str:
    """Проверить подпись ответа Steam и вернуть SteamID64.

    Все полученные ``openid.*`` параметры отправляются обратно в Steam с
    ``openid.mode=check_authentication``: только сам Steam может подтвердить
    свою подпись. Заодно проверяем, что ответ выдан именно нашему callback.
    """
    openid_params = {
        key: value
        for key, value in params.items()
        if key.startswith("openid.")
    }
    if not openid_params:
        raise SteamAuthError("Steam не вернул параметры OpenID")

    if openid_params.get("openid.return_to") != expected_return_to:
        raise SteamAuthError("Ответ Steam адресован другому сайту")

    openid_params["openid.mode"] = "check_authentication"
    body = urllib.parse.urlencode(openid_params).encode()
    request = urllib.request.Request(
        OPENID_ENDPOINT,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            text = response.read().decode("utf-8", "ignore")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SteamAuthError(f"Не удалось связаться со Steam: {exc}") from exc

    if "is_valid:true" not in {line.strip() for line in text.splitlines()}:
        raise SteamAuthError("Steam не подтвердил подпись ответа")

    claimed_id = openid_params.get("openid.claimed_id", "")
    match = STEAM_ID_RE.match(claimed_id)
    if not match:
        raise SteamAuthError("Steam вернул неизвестный идентификатор")
    return match.group(1)


def fetch_profile(steam_id: str) -> dict[str, str]:
    """Публичные ник и аватар из Steam Web API.

    Без ключа или при ошибке сети возвращаем пустой словарь: вход важнее
    красивого имени, поэтому сбой профиля не должен его блокировать.
    """
    if not settings.STEAM_API_KEY:
        return {}

    query = urllib.parse.urlencode(
        {"key": settings.STEAM_API_KEY, "steamids": steam_id}
    )
    try:
        with urllib.request.urlopen(
            f"{PLAYER_SUMMARIES_URL}?{query}", timeout=REQUEST_TIMEOUT
        ) as response:
            data = json.loads(response.read().decode("utf-8", "ignore"))
        players = (data.get("response") or {}).get("players") or []
        player = players[0]
        return {
            "persona_name": (player.get("personaname") or "")[:100],
            "avatar_url": player.get("avatarfull") or "",
        }
    except (
        urllib.error.URLError,
        TimeoutError,
        ValueError,
        AttributeError,
        IndexError,
        TypeError,
    ):
        # Профиль необязателен: вход должен работать и при сбое Web API.
        return {}


def get_or_create_user(steam_id: str, profile: dict[str, str]):
    """Найти или создать пользователя по SteamID64.

    Имя пользователя техническое и стабильное (``steam_<id>``): ник в Steam
    можно сменить, а ссылки и отчёты должны остаться на месте. Для показа
    берётся ник из ``SteamProfile``.
    """
    from django.contrib.auth.models import User

    from games.models import SteamProfile
    from games.services.permissions import sync_admin_flags

    steam_profile = (
        SteamProfile.objects.select_related("user")
        .filter(steam_id=steam_id)
        .first()
    )
    if steam_profile is not None:
        _update_profile(steam_profile, profile)
        sync_admin_flags(steam_profile.user, steam_id)
        return steam_profile.user

    user, _ = User.objects.get_or_create(username=f"steam_{steam_id}")
    SteamProfile.objects.create(
        user=user,
        steam_id=steam_id,
        persona_name=profile.get("persona_name", ""),
        avatar_url=profile.get("avatar_url", ""),
    )
    sync_admin_flags(user, steam_id)
    return user


def _update_profile(steam_profile, profile: dict[str, str]) -> None:
    """Обновить публичные данные, не затирая их пустым ответом."""
    changed: list[str] = []
    persona_name = profile.get("persona_name", "")
    avatar_url = profile.get("avatar_url", "")
    if persona_name and persona_name != steam_profile.persona_name:
        steam_profile.persona_name = persona_name
        changed.append("persona_name")
    if avatar_url and avatar_url != steam_profile.avatar_url:
        steam_profile.avatar_url = avatar_url
        changed.append("avatar_url")
    if changed:
        steam_profile.save(update_fields=[*changed, "updated"])
