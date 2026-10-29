"""Корневые маршруты проекта."""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from games import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    # Парольного входа на сайте нет: этот адрес сразу уводит в Steam.
    path("accounts/login/", views.steam_login, name="login"),
    path("accounts/steam/callback/", views.steam_callback, name="steam_callback"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("games.urls")),
]
