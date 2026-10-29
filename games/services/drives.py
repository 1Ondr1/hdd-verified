"""Накопители: определение класса по характеристикам.

Пользователь вводит полное название диска, но на оценку влияют только
обороты и технология записи. Производитель и модель не важны: два диска
с одинаковыми характеристиками ведут себя в играх одинаково.
"""

from __future__ import annotations

from games.models import DriveProfile

#: Порог, с которого диск считается быстрым. Всё, что медленнее, — 5400.
FAST_RPM = 7200


def profile_for(*, rpm: int | None = None, smr: bool | None = None) -> DriveProfile | None:
    """Определить профиль по характеристикам.

    SMR важнее оборотов: черепичная запись меняет поведение сильнее, чем
    разница между 5400 и 7200. Если обороты неизвестны и SMR не отмечен,
    профиль остаётся пустым — отчёт попадёт только в общую оценку.
    """
    if smr:
        slug = "hdd-smr"
    elif rpm and rpm >= FAST_RPM:
        slug = "hdd-7200-cmr"
    elif rpm:
        slug = "hdd-5400-cmr"
    else:
        return None

    return DriveProfile.objects.filter(slug=slug).first()
