"""Игры: получение из магазинов и сохранение в каталог."""

from __future__ import annotations

from django.db import IntegrityError

from games.models import Game
from games.services import epic, steam
from games.services.catalog import normalize_title

#: Какой клиент умеет собрать карточку для каждого магазина.
_LOADERS = {
    Game.Source.STEAM: steam.game_payload,
    Game.Source.EPIC: epic.game_payload,
}


def get_or_create_game(source: str, external_id: str) -> Game:
    """Вернуть игру из каталога, при необходимости загрузив её из магазина.

    Если Epic-игра уже есть в каталоге из Steam, возвращаем steam-запись:
    приоритет у Steam, а не у магазина, по ссылке из которого пришли.
    """
    game = Game.objects.filter(source=source, external_id=external_id).first()
    if game is not None:
        return game

    payload = _load_payload(source, external_id)

    if source == Game.Source.EPIC:
        twin = _steam_twin(payload)
        if twin is not None:
            return twin

    try:
        return Game.objects.create(**payload)
    except IntegrityError:
        # Параллельный запрос уже создал игру.
        return Game.objects.get(source=source, external_id=external_id)


def refresh_game(game: Game) -> Game:
    """Обновить карточку игры данными из магазина."""
    for field, value in _load_payload(game.source, game.external_id).items():
        setattr(game, field, value)
    game.save()
    return game


def _load_payload(source: str, external_id: str) -> dict:
    try:
        loader = _LOADERS[source]
    except KeyError:
        raise ValueError(f"Неизвестный магазин: {source}") from None
    return loader(external_id)


def _steam_twin(payload: dict) -> Game | None:
    """Найти steam-версию игры, которую собираемся добавить из Epic."""
    keys = {
        normalize_title(payload.get("title", "")),
        normalize_title(payload.get("title_en", "")),
    } - {""}
    if not keys:
        return None

    for game in Game.objects.filter(source=Game.Source.STEAM).only(
        "id", "source", "external_id", "title", "title_en"
    ):
        game_keys = {normalize_title(game.title), normalize_title(game.title_en)} - {""}
        if keys & game_keys:
            return game
    return None
