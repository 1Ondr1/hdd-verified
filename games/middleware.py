"""Middleware банов.

Обычный бан запрещает писать, поэтому здесь проверяется только полный
бан: он закрывает и чтение. Запрет на запись добавляется к конкретным
POST-представлениям декоратором ``block_banned``.
"""

from __future__ import annotations

from django.conf import settings
from django.shortcuts import render
from django.urls import reverse

from games.services.permissions import active_ban


class BanMiddleware:
    """Положить действующий бан в запрос и закрыть сайт при полном бане."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.ban = None
        if request.user.is_authenticated:
            request.ban = active_ban(request.user)

        if request.ban and request.ban.full and not self._is_allowed(request.path):
            return render(
                request,
                "games/banned.html",
                {"ban": request.ban},
                status=403,
            )
        return self.get_response(request)

    @staticmethod
    def _is_allowed(path: str) -> bool:
        """Страницы, без которых забаненный не сможет даже выйти."""
        prefixes = [
            settings.STATIC_URL,
            settings.MEDIA_URL,
            settings.ADMIN_PATH,
            "/health/",
            "/favicon.ico",
        ]
        # MEDIA_URL по умолчанию «/» — такой префикс пропускал бы всё.
        if any(
            prefix and prefix != "/" and path.startswith(prefix)
            for prefix in prefixes
        ):
            return True
        return path in {reverse("logout"), reverse("login")}
