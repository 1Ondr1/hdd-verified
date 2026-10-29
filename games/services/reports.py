"""Сохранение отчётов с учётом ограничений уникальности."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.utils import timezone

from games.models import Game, Report, UserDrive


def save_report(
    *,
    game: Game,
    user: User,
    user_drive: UserDrive | None,
    verdict: str,
    **fields,
) -> Report:
    """Создать или обновить отчёт пользователя об игре.

    У пользователя одна оценка на игру: если он сменил накопитель, удалил
    его из профиля или передумал, новая оценка перезаписывает старую.

    Название и характеристики диска сохраняются в отчёте как снимок —
    история остаётся читаемой даже после удаления накопителя. Размер игры
    тоже становится снимком, но с отдельной датой: редактирование вердикта
    не должно делать старый размер «свежим».
    """
    existing = Report.objects.filter(game=game, user=user).first()
    size = fields.get("install_size_gb")

    defaults = {
        "drive_name": user_drive.name if user_drive else "",
        "drive_specs": user_drive.specs if user_drive else "",
        "drive_capacity_gb": user_drive.capacity_gb if user_drive else None,
        "drive_rpm": user_drive.rpm if user_drive else None,
        "drive_smr": user_drive.smr if user_drive else None,
        "profile": user_drive.profile if user_drive else None,
        "verdict": verdict,
        **fields,
    }
    if existing is None or existing.install_size_gb != size:
        defaults["install_size_updated"] = timezone.now() if size else None

    report, _ = Report.objects.update_or_create(
        game=game, user=user, defaults=defaults
    )
    return report
