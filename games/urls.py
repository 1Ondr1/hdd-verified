"""Маршруты приложения ``games``."""

from django.urls import path

from games import views

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.search, name="search"),
    path("api/games/", views.game_search_api, name="game_search_api"),
    # Отчёт — раньше карточки: старый адрес ``/game/<appid>/report/`` тоже
    # состоит из трёх сегментов и иначе попал бы в общий маршрут игры.
    path(
        "game/<str:source>/<str:external_id>/report/",
        views.submit_report,
        name="submit_report",
    ),
    path("game/<int:appid>/report/", views.legacy_submit_report, name="legacy_submit_report"),
    path("reports/<int:pk>/translate/", views.translate_comment, name="translate_comment"),
    path("reports/<int:pk>/like/", views.toggle_like, name="toggle_like"),
    path("reports/<int:pk>/complain/", views.complain, name="complain"),
    path("reports/<int:pk>/delete/", views.delete_report, name="delete_report"),
    path("game/<str:source>/<str:external_id>/", views.game_detail, name="game_detail"),
    path("game/<int:appid>/", views.legacy_game_detail, name="legacy_game_detail"),
    path("drives/", views.my_drives, name="my_drives"),
    path("drives/add/", views.add_drive, name="add_drive"),
    path("drives/<int:pk>/remove/", views.remove_drive, name="remove_drive"),
]
