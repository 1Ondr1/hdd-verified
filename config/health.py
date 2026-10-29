"""Проверка живости для хостинга.

Render (и любой другой балансировщик) опрашивает этот адрес, чтобы
понять, поднимать ли инстанс. Отдаём только статус: ни версии, ни
деталей конфигурации наружу не попадает.
"""

from __future__ import annotations

from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@never_cache
@require_GET
def health(request: HttpRequest) -> JsonResponse:
    """Ответить 200, если база отвечает, иначе 503."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:  # любая ошибка БД значит «не готов»
        return JsonResponse({"status": "error"}, status=503)
    return JsonResponse({"status": "ok"})
