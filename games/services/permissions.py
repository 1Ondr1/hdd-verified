"""Права: администраторы по SteamID64 и проверка банов."""

from __future__ import annotations

from functools import wraps

from django.conf import settings
from django.shortcuts import render

from games.models import Ban, SteamProfile


def steam_id_for(user) -> str:
    """Вернуть SteamID64 пользователя или пустую строку.

    Профиль может отсутствовать у старых парольных аккаунтов — такие
    пользователи не считаются администраторами и не банятся по SteamID.
    """
    if not getattr(user, "is_authenticated", False):
        return ""
    try:
        return user.steam_profile.steam_id
    except SteamProfile.DoesNotExist:
        return ""


def is_admin_steam_id(steam_id: str) -> bool:
    """Входит ли SteamID64 в список администраторов из окружения."""
    return bool(steam_id) and steam_id in settings.ADMIN_STEAM_IDS


def is_admin_user(user) -> bool:
    """Может ли пользователь открыть админку."""
    return bool(
        getattr(user, "is_active", False)
        and is_admin_steam_id(steam_id_for(user))
    )


def active_ban(user) -> Ban | None:
    """Действующий бан пользователя, если он есть."""
    steam_id = steam_id_for(user)
    if not steam_id:
        return None
    return Ban.objects.filter(steam_id=steam_id, active=True).first()


def block_banned(view):
    """Запретить действие, если у пользователя действующий бан.

    Ставится после ``login_required``: анонимного пользователя сначала
    отправляем в Steam, а уже потом проверяем бан.
    """

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        ban = getattr(request, "ban", None) or active_ban(request.user)
        if ban:
            return render(
                request, "games/banned.html", {"ban": ban}, status=403
            )
        return view(request, *args, **kwargs)

    return wrapper


def sync_admin_flags(user, steam_id: str) -> None:
    """Выдать или снять права staff/superuser по allowlist.

    Вызывается при входе через Steam. Источник правды — переменная
    окружения: смена ``DJANGO_ADMIN_STEAM_IDS`` и перезапуск немедленно
    закрывают админку прежнему администратору (проверка в AdminSite),
    а новый получает флаги при следующем входе.
    """
    should_be_admin = is_admin_steam_id(steam_id)
    fields: list[str] = []
    if user.is_staff != should_be_admin:
        user.is_staff = should_be_admin
        fields.append("is_staff")
    if user.is_superuser != should_be_admin:
        user.is_superuser = should_be_admin
        fields.append("is_superuser")
    if fields:
        user.save(update_fields=fields)
