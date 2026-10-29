"""Базовые профили накопителей.

Профили задают «оси», по которым сравниваются игры. Пять классов покрывают
почти весь пользовательский опыт; отдельные модели уточняют SMR и кэш.
"""

from django.db import migrations

PROFILES = (
    ("nvme", "NVMe", "ssd", 10),
    ("ssd-sata", "SSD SATA", "ssd", 20),
    ("hdd-7200-cmr", "HDD 7200 CMR", "hdd", 30),
    ("hdd-5400-cmr", "HDD 5400 CMR", "hdd", 40),
    ("hdd-smr", "HDD SMR", "hdd", 50),
)


def seed_profiles(apps, schema_editor):
    DriveProfile = apps.get_model("games", "DriveProfile")
    for slug, label, kind, sort_order in PROFILES:
        DriveProfile.objects.update_or_create(
            slug=slug,
            defaults={"label": label, "kind": kind, "sort_order": sort_order},
        )


def remove_profiles(apps, schema_editor):
    DriveProfile = apps.get_model("games", "DriveProfile")
    DriveProfile.objects.filter(slug__in=[slug for slug, *_ in PROFILES]).delete()


class Migration(migrations.Migration):
    dependencies = [("games", "0001_initial")]

    operations = [migrations.RunPython(seed_profiles, remove_profiles)]
