"""Теги для переводов интерфейса."""

from __future__ import annotations

from django import template

from games.i18n import translate, translate_plural

register = template.Library()


@register.simple_tag
def t(key: str, **params) -> str:
    """Вставить переведённую строку: ``{% t "nav.games" %}``."""
    return translate(key, **params)


@register.simple_tag
def tn(key: str, n: int, **params) -> str:
    """Строка с числом и верной формой: ``{% tn "game.reports_count" 3 %}``."""
    return translate_plural(key, n, **params)
