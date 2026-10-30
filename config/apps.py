"""Конфигурация приложений проекта."""

from django.contrib.admin.apps import AdminConfig


class SteamAdminConfig(AdminConfig):
    """Стандартная админка, но с доступом по SteamID64."""

    default_site = "games.admin_site.SteamAdminSite"
