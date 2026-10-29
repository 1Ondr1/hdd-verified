"""Локализованные описания игр и структурированные снимки отчётов.

* У игры появляются английские жанр и описание — переключатель языка
  показывает их вместо русских.
* У отчёта появляются поля-снимки характеристик диска. По ним работает
  фильтр отчётов; раньше характеристики лежали только строкой.
* Размер игры можно указывать в отчёте. Дата замера отдельная, чтобы
  редактирование вердикта не делало старый размер свежим.
"""

from __future__ import annotations

import re

from django.db import migrations, models

_CAPACITY_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ТБ|ГБ|TB|GB)", re.I)
_PROFILE_SPECS = {
    "hdd-7200-cmr": (7200, False),
    "hdd-5400-cmr": (5400, False),
    "hdd-smr": (None, True),
}


def _capacity(text: str) -> int | None:
    match = _CAPACITY_RE.search(text or "")
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    if match.group(2).lower() in {"тб", "tb"}:
        value *= 1000
    return int(round(value))


def backfill_report_snapshots(apps, schema_editor):
    """Заполнить новые поля из диска пользователя или старого снимка."""
    UserDrive = apps.get_model("games", "UserDrive")
    Report = apps.get_model("games", "Report")

    for report in Report.objects.select_related("profile"):
        drive = (
            UserDrive.objects.filter(user_id=report.user_id, name=report.drive_name).first()
            if report.drive_name
            else None
        )
        if drive is not None:
            capacity = drive.capacity_gb
            rpm = drive.rpm
            smr = drive.smr
        else:
            capacity = _capacity(report.drive_specs)
            rpm, smr = _PROFILE_SPECS.get(
                report.profile.slug if report.profile else "", (None, None)
            )

        Report.objects.filter(pk=report.pk).update(
            drive_capacity_gb=capacity,
            drive_rpm=rpm,
            drive_smr=smr,
        )


class Migration(migrations.Migration):
    dependencies = [("games", "0006_drives_by_specs")]

    operations = [
        migrations.AddField(
            model_name="game",
            name="genre_en",
            field=models.CharField(
                blank=True, max_length=100, verbose_name="жанр на английском"
            ),
        ),
        migrations.AddField(
            model_name="game",
            name="short_description_en",
            field=models.TextField(
                blank=True, verbose_name="краткое описание на английском"
            ),
        ),
        migrations.AddField(
            model_name="report",
            name="drive_capacity_gb",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="объём накопителя, ГБ"
            ),
        ),
        migrations.AddField(
            model_name="report",
            name="drive_rpm",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True, verbose_name="обороты накопителя"
            ),
        ),
        migrations.AddField(
            model_name="report",
            name="drive_smr",
            field=models.BooleanField(
                blank=True,
                help_text="Пусто — неизвестно",
                null=True,
                verbose_name="SMR накопителя",
            ),
        ),
        migrations.AddField(
            model_name="report",
            name="install_size_gb",
            field=models.FloatField(
                blank=True,
                help_text="Сколько игра занимает на диске",
                null=True,
                verbose_name="размер игры, ГБ",
            ),
        ),
        migrations.AddField(
            model_name="report",
            name="install_size_updated",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="размер обновлён"
            ),
        ),
        migrations.RunPython(backfill_report_snapshots, migrations.RunPython.noop),
    ]
