"""Накопители описываются характеристиками, а не моделью.

* Справочник моделей и альтернативные написания удаляются.
* У накопителя пользователя остаются полное название и три характеристики:
  объём, обороты и технология записи.
* Отчёт хранит снимок названия и характеристик, поэтому удаление диска
  из профиля не ломает историю.
* SSD-профили убираются: сайт про жёсткие диски.
"""

from django.db import migrations, models


def describe(drive) -> str:
    """Полное название модели для показа."""
    return " ".join(
        filter(None, [drive.vendor, drive.family, drive.model_number])
    ).strip() or drive.model_number


def specs(drive) -> str:
    """Характеристики в том же виде, что показывает интерфейс."""
    parts = []
    if drive.capacity_gb:
        gb = drive.capacity_gb
        parts.append(
            f"{gb // 1000} ТБ" if gb >= 1000 and gb % 1000 == 0 else f"{gb} ГБ"
        )
    if drive.rpm:
        parts.append(f"{drive.rpm} об/мин")
    if drive.smr is True:
        parts.append("SMR")
    elif drive.smr is False:
        parts.append("CMR")
    return " · ".join(parts)


def copy_drive_data(apps, schema_editor):
    UserDrive = apps.get_model("games", "UserDrive")
    Report = apps.get_model("games", "Report")

    used: set[tuple[int, str]] = set()
    for item in UserDrive.objects.select_related("drive").order_by("user_id", "pk"):
        drive = item.drive
        name = describe(drive)
        if (item.user_id, name) in used:
            name = f"{name} (№{item.pk})"
        used.add((item.user_id, name))

        UserDrive.objects.filter(pk=item.pk).update(
            name=name,
            capacity_gb=drive.capacity_gb,
            rpm=drive.rpm,
            smr=drive.smr,
            profile_id=drive.profile_id,
        )

    for report in Report.objects.select_related("drive").filter(drive__isnull=False):
        Report.objects.filter(pk=report.pk).update(
            drive_name=describe(report.drive),
            drive_specs=specs(report.drive),
            profile_id=report.profile_id or report.drive.profile_id,
        )


def remove_ssd_profiles(apps, schema_editor):
    DriveProfile = apps.get_model("games", "DriveProfile")
    DriveProfile.objects.filter(slug__in=("nvme", "ssd-sata")).delete()


class Migration(migrations.Migration):
    dependencies = [("games", "0005_unify_games_and_reports")]

    operations = [
        # --- Накопитель: название и три характеристики ----------------------
        migrations.AddField(
            model_name="userdrive",
            name="name",
            field=models.CharField(default="", max_length=200, verbose_name="название"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="userdrive",
            name="capacity_gb",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="объём, ГБ"
            ),
        ),
        migrations.AddField(
            model_name="userdrive",
            name="rpm",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True, verbose_name="об/мин"
            ),
        ),
        migrations.AddField(
            model_name="userdrive",
            name="smr",
            field=models.BooleanField(
                blank=True, help_text="Пусто — неизвестно", null=True, verbose_name="SMR"
            ),
        ),
        migrations.AddField(
            model_name="userdrive",
            name="profile",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="owners",
                to="games.driveprofile",
                verbose_name="профиль",
            ),
        ),
        # --- Отчёт: снимок накопителя --------------------------------------
        migrations.AddField(
            model_name="report",
            name="drive_name",
            field=models.CharField(
                blank=True, default="", max_length=200, verbose_name="накопитель"
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="report",
            name="drive_specs",
            field=models.CharField(
                blank=True,
                default="",
                max_length=200,
                verbose_name="характеристики накопителя",
            ),
            preserve_default=False,
        ),
        migrations.RunPython(copy_drive_data, migrations.RunPython.noop),
        # --- Убираем справочник моделей и связь с ним -----------------------
        migrations.RemoveConstraint(
            model_name="userdrive", name="uniq_user_drive"
        ),
        migrations.RemoveField(model_name="userdrive", name="drive"),
        migrations.AlterModelOptions(
            name="userdrive",
            options={
                "ordering": ("-is_primary", "name"),
                "verbose_name": "накопитель пользователя",
                "verbose_name_plural": "накопители пользователей",
            },
        ),
        migrations.AddConstraint(
            model_name="userdrive",
            constraint=models.UniqueConstraint(
                fields=("user", "name"), name="uniq_user_drive_name"
            ),
        ),
        migrations.AlterField(
            model_name="report",
            name="profile",
            field=models.ForeignKey(
                blank=True,
                help_text="Заполняется автоматически по характеристикам накопителя",
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="reports",
                to="games.driveprofile",
                verbose_name="профиль",
            ),
        ),
        migrations.RemoveField(model_name="report", name="drive"),
        migrations.DeleteModel(name="DriveAlias"),
        migrations.DeleteModel(name="DriveModel"),
        # --- Только жёсткие диски ------------------------------------------
        migrations.RemoveField(model_name="driveprofile", name="kind"),
        migrations.RunPython(remove_ssd_profiles, migrations.RunPython.noop),
    ]
