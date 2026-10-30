"""Корневые маршруты проекта."""

from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.templatetags.static import static
from django.urls import include, path
from django.views.generic import RedirectView

from config.health import health
from games import views

urlpatterns = [
    path("health/", health, name="health"),
    # Браузеры по-прежнему просят /favicon.ico, даже если в разметке
    # указан SVG: уводим их на актуальную иконку.
    path(
        "favicon.ico",
        RedirectView.as_view(url=static("games/favicon.svg"), permanent=True),
        name="favicon",
    ),
    path(settings.ADMIN_PATH, admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    # Парольного входа на сайте нет: этот адрес сразу уводит в Steam.
    path("accounts/login/", views.steam_login, name="login"),
    path("accounts/steam/callback/", views.steam_callback, name="steam_callback"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("games.urls")),
]
