"""Админка только для Steam-администраторов.

Парольной формы нет: неавторизованный посетитель сразу уходит на вход
через Steam. Доступ проверяется по SteamID64 из ``DJANGO_ADMIN_STEAM_IDS``
на каждом запросе, поэтому смена списка в окружении действует сразу
после перезапуска, даже если у пользователя остались старые флаги.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.contrib.admin import AdminSite
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import reverse

from games.services.permissions import is_admin_user


class SteamAdminSite(AdminSite):
    site_header = "HDD Verified"
    site_title = "HDD Verified"
    index_title = "Управление каталогом"

    def has_permission(self, request: HttpRequest) -> bool:
        return is_admin_user(request.user)

    def login(self, request: HttpRequest, extra_context=None):
        if request.method == "GET" and self.has_permission(request):
            return HttpResponseRedirect(
                reverse("admin:index", current_app=self.name)
            )
        next_url = request.get_full_path()
        return HttpResponseRedirect(
            f"{reverse('login')}?{urlencode({'next': next_url})}"
        )
