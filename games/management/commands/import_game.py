"""Добавление игр в каталог из Steam Store и Epic Games Store."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from games.models import Game
from games.services import epic, steam
from games.services.epic import is_valid_external_id
from games.services.games import get_or_create_game, refresh_game


class Command(BaseCommand):
    help = (
        "Добавить игру из Steam по AppID или из Epic по namespace:id, "
        "либо обновить уже добавленную"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "game_id",
            help="Steam AppID (например 1091500) или epic:<namespace>:<id>",
        )
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="Обновить данные игры, если она уже есть в каталоге",
        )

    def handle(self, *args, **options):
        source, external_id = self._parse_id(options["game_id"])

        try:
            game = Game.objects.filter(source=source, external_id=external_id).first()
            if options["refresh"] and game is not None:
                game = refresh_game(game)
                action = "Обновлена"
            else:
                game = get_or_create_game(source, external_id)
                action = "В каталоге"
        except (steam.SteamError, epic.EpicError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"{action}: {game.display_title} ({game.source}/{game.external_id})"
            )
        )

    @staticmethod
    def _parse_id(raw: str) -> tuple[str, str]:
        raw = (raw or "").strip()
        if raw.lower().startswith("epic:"):
            external_id = raw[5:]
            if not is_valid_external_id(external_id):
                raise CommandError("Ожидается epic:<namespace>:<id>")
            return Game.Source.EPIC, external_id
        if not raw.isdigit():
            raise CommandError("Steam AppID должен состоять из цифр")
        return Game.Source.STEAM, raw
