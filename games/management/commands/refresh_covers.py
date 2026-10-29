"""Обновление обложек Steam: широкий арт со страницы магазина.

Steam отдаёт обложки по хешированным адресам, которые меняются вместе с
артом. Угаданные пути в старом формате CDN либо устаревают (CS2 показывал
обложку CS:GO), либо отсутствуют. Поэтому адреса перечитываются со
страницы магазина, а команда обновляет уже сохранённые игры.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from games.models import Game
from games.services import steam


class Command(BaseCommand):
    help = "Перечитать обложки Steam со страниц магазина (все игры или один AppID)"

    def add_arguments(self, parser):
        parser.add_argument(
            "game_id",
            nargs="?",
            help="Steam AppID; без него обновляются все игры каталога",
        )

    def handle(self, *args, **options):
        games = Game.objects.filter(source=Game.Source.STEAM)
        if options["game_id"]:
            games = games.filter(external_id=options["game_id"])

        updated = 0
        for game in games.order_by("pk"):
            if not game.external_id.isdigit():
                continue
            appid = int(game.external_id)
            base = steam.store_capsule(appid, "english")
            localized = steam.store_capsule(appid, "russian")
            if not base and not localized:
                self.stderr.write(f"Обложка не найдена: {game.display_title}")
                continue

            game.cover_url = base or game.cover_url
            game.cover_url_ru = localized or game.cover_url_ru
            game.save(update_fields=["cover_url", "cover_url_ru"])
            updated += 1

        self.stdout.write(self.style.SUCCESS(f"Обложек обновлено: {updated}"))
