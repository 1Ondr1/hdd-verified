"""Единый формат игр (Steam + Epic) и одна оценка на пользователя.

* ``Game`` получает ``source``/``external_id`` вместо жёсткого ``steam_appid``,
  а также ``title_en`` и ``store_url``. Старые игры — из Steam.
* ``UserDrive.label`` удаляется: подпись дублировала модель и ни на что
  не влияла.
* Отчёты становятся уникальными по ``(game, user)``. Дубликаты, возникшие
  при удалении диска, схлопываются: остаётся отчёт с накопителем, иначе
  самый свежий.
"""

from django.db import migrations, models
from django.db.models import Count


def merge_duplicate_reports(apps, schema_editor):
    Report = apps.get_model("games", "Report")
    duplicates = (
        Report.objects.values("game_id", "user_id")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
    )
    for row in duplicates:
        reports = Report.objects.filter(
            game_id=row["game_id"], user_id=row["user_id"]
        )
        # Отчёт с накопителем информативнее «безадресного».
        keep = (
            reports.exclude(drive=None).order_by("-updated").first()
            or reports.order_by("-updated").first()
        )
        reports.exclude(pk=keep.pk).delete()


def fill_game_source(apps, schema_editor):
    Game = apps.get_model("games", "Game")
    for game in Game.objects.all().only("pk", "steam_appid"):
        appid = game.steam_appid
        Game.objects.filter(pk=game.pk).update(
            source="steam",
            external_id=str(appid),
            store_url=f"https://store.steampowered.com/app/{appid}/",
        )


class Migration(migrations.Migration):
    dependencies = [("games", "0004_report_load_speed")]

    operations = [
        # --- Отчёты: одна оценка на игру -----------------------------------
        migrations.RemoveConstraint(
            model_name="report", name="uniq_report_game_user_drive"
        ),
        migrations.RemoveConstraint(
            model_name="report", name="uniq_report_game_user_nodrive"
        ),
        migrations.RunPython(merge_duplicate_reports, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="report",
            constraint=models.UniqueConstraint(
                fields=("game", "user"), name="uniq_report_game_user"
            ),
        ),
        # --- Накопители: подпись больше не нужна ---------------------------
        migrations.RemoveField(model_name="userdrive", name="label"),
        # --- Игры: магазин + два языка -------------------------------------
        migrations.AddField(
            model_name="game",
            name="source",
            field=models.CharField(
                choices=[("steam", "Steam"), ("epic", "Epic Games")],
                default="steam",
                max_length=10,
                verbose_name="магазин",
            ),
        ),
        migrations.AddField(
            model_name="game",
            name="external_id",
            field=models.CharField(
                default="", max_length=100, verbose_name="идентификатор в магазине"
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="game",
            name="title_en",
            field=models.CharField(
                blank=True,
                default="",
                max_length=200,
                verbose_name="название на английском",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="game",
            name="store_url",
            field=models.URLField(
                blank=True,
                default="",
                max_length=500,
                verbose_name="страница магазина",
            ),
            preserve_default=False,
        ),
        migrations.RunPython(fill_game_source, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="game",
            constraint=models.UniqueConstraint(
                fields=("source", "external_id"), name="uniq_game_source_external"
            ),
        ),
        migrations.RemoveField(model_name="game", name="steam_appid"),
    ]
