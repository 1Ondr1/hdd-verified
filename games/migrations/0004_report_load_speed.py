"""Загрузка до меню — диапазоны вместо секунд; размер установки убран.

Размер установки уже приходит из требований Steam, а введённое вручную
значение нигде не использовалось. Точные секунды загрузки пользователи
почти не замеряют, поэтому старые значения переводятся в диапазоны.
"""

from django.db import migrations, models

LOAD_SPEED_CHOICES = [
    ("fast", "Быстро — до 15 с"),
    ("normal", "Нормально — 15–60 с"),
    ("slow", "Долго — 1–3 мин"),
    ("very_slow", "Очень долго — больше 3 мин"),
]

#: Середина диапазона — на случай отката миграции.
REPRESENTATIVE_SECONDS = {
    "fast": 10.0,
    "normal": 30.0,
    "slow": 90.0,
    "very_slow": 300.0,
}


def _seconds_to_speed(seconds: float | None) -> str:
    if seconds is None:
        return ""
    if seconds < 15:
        return "fast"
    if seconds < 60:
        return "normal"
    if seconds < 180:
        return "slow"
    return "very_slow"


def forwards(apps, schema_editor):
    Report = apps.get_model("games", "Report")
    reports = Report.objects.exclude(load_to_menu_sec=None).only("id", "load_to_menu_sec")
    for report in reports:
        Report.objects.filter(pk=report.pk).update(
            load_speed=_seconds_to_speed(report.load_to_menu_sec)
        )


def backwards(apps, schema_editor):
    Report = apps.get_model("games", "Report")
    reports = Report.objects.exclude(load_speed="").only("id", "load_speed")
    for report in reports:
        Report.objects.filter(pk=report.pk).update(
            load_to_menu_sec=REPRESENTATIVE_SECONDS.get(report.load_speed)
        )


class Migration(migrations.Migration):
    dependencies = [("games", "0003_alter_report_drive")]

    operations = [
        migrations.AddField(
            model_name="report",
            name="load_speed",
            field=models.CharField(
                blank=True,
                choices=LOAD_SPEED_CHOICES,
                max_length=10,
                verbose_name="загрузка до меню",
            ),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(model_name="report", name="install_size_gb"),
        migrations.RemoveField(model_name="report", name="load_to_menu_sec"),
    ]
