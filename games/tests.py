"""Тесты каталога, накопителей и агрегации отчётов."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation

from games.forms import AddDriveForm, ReportFilterForm, ReportForm
from games.i18n import translate_plural
from games.models import (
    CommentTranslation,
    DriveProfile,
    Game,
    Report,
    SteamProfile,
    UserDrive,
)
from games.services import epic, stats, steam, steam_auth
from games.services import search as game_search
from games.services import translate as comment_translate
from games.services.reports import save_report
from games.services.catalog import SearchResult, normalize_title
from games.services.drives import profile_for
from games.services.requirements import requires_ssd, storage_gb


class ProfileFixtureMixin:
    """Профили, которые в реальной базе создаются миграцией."""

    profiles = {
        "hdd-7200-cmr": ("HDD 7200 CMR", 10),
        "hdd-5400-cmr": ("HDD 5400 CMR", 20),
        "hdd-smr": ("HDD SMR", 30),
    }

    @classmethod
    def setUpTestData(cls):
        # Профили создаются миграцией, но тесты не должны на это полагаться.
        for slug, (label, order) in cls.profiles.items():
            DriveProfile.objects.get_or_create(
                slug=slug, defaults={"label": label, "sort_order": order}
            )


class DriveProfileTests(ProfileFixtureMixin, TestCase):
    def test_profile_by_rpm_and_recording(self):
        self.assertEqual(profile_for(rpm=7200).slug, "hdd-7200-cmr")
        self.assertEqual(profile_for(rpm=5400).slug, "hdd-5400-cmr")
        self.assertEqual(profile_for(rpm=5400, smr=True).slug, "hdd-smr")

    def test_smr_wins_over_rpm(self):
        self.assertEqual(profile_for(rpm=7200, smr=True).slug, "hdd-smr")

    def test_unknown_specs_give_no_profile(self):
        self.assertIsNone(profile_for())
        self.assertIsNone(profile_for(smr=False))

    def test_ssd_profiles_are_gone(self):
        self.assertFalse(
            DriveProfile.objects.filter(slug__in=("nvme", "ssd-sata")).exists()
        )


class UserDriveTests(TestCase):
    def test_specs_text(self):
        drive = UserDrive(
            name="Seagate ST2000DM008", capacity_gb=2000, rpm=7200, smr=False
        )
        self.assertEqual(drive.specs, "2 ТБ · 7200 об/мин · CMR")

    def test_specs_skip_unknown_recording(self):
        drive = UserDrive(name="WD Blue", capacity_gb=500, rpm=5400, smr=None)
        self.assertEqual(drive.specs, "500 ГБ · 5400 об/мин")

    def test_unknown_capacity_is_not_shown(self):
        drive = UserDrive(name="Old drive", rpm=5400, smr=True)
        self.assertEqual(drive.specs, "5400 об/мин · SMR")


class AddDriveFormTests(ProfileFixtureMixin, TestCase):
    def test_form_has_three_characteristics(self):
        form = AddDriveForm()
        self.assertEqual(
            list(form.fields),
            ["name", "capacity_gb", "rpm", "recording", "is_primary"],
        )

    def test_form_builds_drive_from_dropdowns(self):
        form = AddDriveForm(
            {
                "name": "Seagate Barracuda ST2000DM008",
                "capacity_gb": "2000",
                "rpm": "7200",
                "recording": "cmr",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        drive = form.save(commit=False)

        self.assertEqual(drive.capacity_gb, 2000)
        self.assertEqual(drive.rpm, 7200)
        self.assertFalse(drive.smr)
        self.assertEqual(drive.profile.slug, "hdd-7200-cmr")
        self.assertEqual(drive.specs, "2 ТБ · 7200 об/мин · CMR")

    def test_form_marks_smr(self):
        form = AddDriveForm(
            {
                "name": "WD Blue WD20EZAZ",
                "capacity_gb": "2000",
                "rpm": "5400",
                "recording": "smr",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        drive = form.save(commit=False)

        self.assertTrue(drive.smr)
        self.assertEqual(drive.profile.slug, "hdd-smr")

    def test_form_allows_unknown_characteristics(self):
        form = AddDriveForm({"name": "Unknown drive"})

        self.assertTrue(form.is_valid(), form.errors)
        drive = form.save(commit=False)

        self.assertIsNone(drive.capacity_gb)
        self.assertIsNone(drive.rpm)
        self.assertIsNone(drive.smr)
        self.assertIsNone(drive.profile)
        self.assertEqual(drive.specs, "")

    def test_name_is_required(self):
        form = AddDriveForm({"name": ""})
        self.assertFalse(form.is_valid())


class ReportAggregationTests(ProfileFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.game = Game.objects.create(
            source=Game.Source.STEAM, external_id="1", title="Test Game"
        )
        owner = User.objects.create_user(username="owner", password="pass12345")
        cls.fast = UserDrive.objects.create(
            user=owner,
            name="Fast drive",
            capacity_gb=2000,
            rpm=7200,
            smr=False,
            profile=profile_for(rpm=7200),
        )
        cls.slow = UserDrive.objects.create(
            user=owner,
            name="Slow drive",
            capacity_gb=4000,
            rpm=5400,
            smr=True,
            profile=profile_for(rpm=5400, smr=True),
        )

    def _report(self, username: str, verdict: str, drive: UserDrive | None) -> Report:
        user = User.objects.create_user(username=username, password="pass12345")
        return save_report(
            game=self.game, user=user, user_drive=drive, verdict=verdict
        )

    def test_no_reports_means_no_data(self):
        overall = stats.overall_rating(self.game)
        self.assertEqual(overall.level, stats.LEVEL_NO_DATA)
        self.assertFalse(overall.has_data)

    def test_playable_reports(self):
        self._report("u1", Report.Verdict.PLAYABLE, self.fast)
        self._report("u2", Report.Verdict.PLAYABLE, self.fast)

        overall = stats.overall_rating(self.game)
        self.assertEqual(overall.level, stats.LEVEL_PLAYABLE)
        self.assertEqual(overall.reports, 2)

    def test_unplayable_reports(self):
        self._report("u1", Report.Verdict.UNPLAYABLE, self.fast)
        self._report("u2", Report.Verdict.UNPLAYABLE, self.slow)

        self.assertEqual(stats.overall_rating(self.game).level, stats.LEVEL_UNPLAYABLE)

    def test_reports_without_drive_have_lower_weight(self):
        self._report("u1", Report.Verdict.PLAYABLE, None)
        self._report("u2", Report.Verdict.PLAYABLE, None)

        overall = stats.overall_rating(self.game)
        self.assertEqual(overall.reports, 2)
        self.assertEqual(overall.level, stats.LEVEL_NO_DATA)
        self.assertAlmostEqual(overall.effective_reports, 0.8)

    def test_hidden_reports_are_ignored(self):
        report = self._report("u1", Report.Verdict.PLAYABLE, self.fast)
        report.hidden = True
        report.save(update_fields=["hidden"])

        self.assertEqual(stats.overall_rating(self.game).reports, 0)

    def test_profile_breakdown(self):
        self._report("u1", Report.Verdict.PLAYABLE, self.fast)
        self._report("u2", Report.Verdict.PLAYABLE, self.fast)
        self._report("u3", Report.Verdict.UNPLAYABLE, self.slow)

        rows = {row.slug: row for row in stats.profile_ratings(self.game)}
        self.assertEqual(rows["hdd-7200-cmr"].percent, 100)
        self.assertEqual(rows["hdd-7200-cmr"].reports, 2)
        self.assertEqual(rows["hdd-7200-cmr"].level, stats.LEVEL_PLAYABLE)
        self.assertEqual(rows["hdd-smr"].percent, 0)
        self.assertEqual(rows["hdd-smr"].level, stats.LEVEL_UNPLAYABLE)

    def test_report_stores_drive_snapshot(self):
        report = self._report("u1", Report.Verdict.PLAYABLE, self.fast)

        self.assertEqual(report.drive_name, "Fast drive")
        self.assertEqual(report.drive_specs, "2 ТБ · 7200 об/мин · CMR")
        self.assertEqual(report.profile, self.fast.profile)

    def test_report_is_updated_for_same_user_and_game(self):
        user = User.objects.create_user(username="u1", password="pass12345")
        save_report(
            game=self.game, user=user, user_drive=self.fast,
            verdict=Report.Verdict.PLAYABLE,
        )
        save_report(
            game=self.game, user=user, user_drive=self.slow,
            verdict=Report.Verdict.UNPLAYABLE,
        )

        reports = self.game.reports.filter(user=user)
        self.assertEqual(reports.count(), 1)
        report = reports.get()
        self.assertEqual(report.verdict, Report.Verdict.UNPLAYABLE)
        self.assertEqual(report.drive_name, "Slow drive")

    def test_report_with_drive_replaces_less_precise_one(self):
        user = User.objects.create_user(username="u1", password="pass12345")
        save_report(
            game=self.game, user=user, user_drive=None,
            verdict=Report.Verdict.LIMITED,
        )
        save_report(
            game=self.game, user=user, user_drive=self.fast,
            verdict=Report.Verdict.PLAYABLE,
        )

        reports = self.game.reports.filter(user=user)
        self.assertEqual(reports.count(), 1)
        self.assertEqual(reports.get().drive_name, "Fast drive")
        self.assertEqual(reports.get().profile, self.fast.profile)

    def test_report_without_drive_clears_snapshot(self):
        """Удалил диск — новая оценка перезаписывает старую, а не плодит вторую."""
        user = User.objects.create_user(username="u1", password="pass12345")
        save_report(
            game=self.game, user=user, user_drive=self.fast,
            verdict=Report.Verdict.PLAYABLE,
        )
        save_report(
            game=self.game, user=user, user_drive=None,
            verdict=Report.Verdict.UNPLAYABLE,
        )

        reports = self.game.reports.filter(user=user)
        self.assertEqual(reports.count(), 1)
        report = reports.get()
        self.assertEqual(report.drive_name, "")
        self.assertEqual(report.drive_specs, "")
        self.assertIsNone(report.profile)
        self.assertEqual(report.verdict, Report.Verdict.UNPLAYABLE)


class ReportFilterAndSizeTests(ProfileFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.game = Game.objects.create(
            source=Game.Source.STEAM,
            external_id="200",
            title="Filtered Game",
            storage_gb=70,
        )

    def _report(
        self,
        username: str,
        *,
        capacity: int = 2000,
        rpm: int = 7200,
        smr: bool = False,
        verdict: str = Report.Verdict.PLAYABLE,
        size: float | None = None,
        days_ago: int = 0,
    ) -> Report:
        user = User.objects.create_user(username=username, password="pass12345")
        drive = UserDrive.objects.create(
            user=user,
            name=f"{username} drive",
            capacity_gb=capacity,
            rpm=rpm,
            smr=smr,
            profile=profile_for(rpm=rpm, smr=smr),
        )
        report = save_report(
            game=self.game,
            user=user,
            user_drive=drive,
            verdict=verdict,
            install_size_gb=size,
        )
        if size is not None and days_ago:
            Report.objects.filter(pk=report.pk).update(
                install_size_updated=timezone.now() - timedelta(days=days_ago)
            )
            report.refresh_from_db()
        return report

    def test_filter_by_rpm_and_recording(self):
        fast = self._report("fast", capacity=2000, rpm=7200, smr=False)
        self._report("slow", capacity=2000, rpm=5400, smr=True)

        reports = list(
            stats.filtered_reports(
                self.game, rpm=7200, recording="cmr"
            )
        )

        self.assertEqual([report.pk for report in reports], [fast.pk])

    def test_filter_ignores_unknown_values(self):
        self._report("fast")
        self._report("slow", capacity=4000, rpm=5400, smr=True)

        self.assertEqual(
            stats.filtered_reports(self.game, rpm="not-a-number").count(), 2
        )
        self.assertEqual(stats.filtered_reports(self.game, recording="cmr").count(), 1)
        self.assertEqual(stats.filtered_reports(self.game, recording="smr").count(), 1)

    def test_filter_form_marks_empty_as_any(self):
        form = ReportFilterForm()
        self.assertEqual(form.fields["rpm"].choices[0], ("", "Любые"))
        self.assertEqual(form.fields["recording"].choices[0], ("", "Любые"))
        self.assertNotIn("capacity", form.fields)
        self.assertFalse(form.is_bound)

    def test_view_filters_reports(self):
        self._report("fast")
        self._report("slow", capacity=4000, rpm=5400, smr=True)

        response = self.client.get(
            reverse("game_detail", args=["steam", "200"]),
            {"rpm": "5400", "recording": "smr"},
        )

        self.assertTrue(response.context["filter_active"])
        self.assertEqual(len(response.context["reports"]), 1)
        self.assertContains(response, "slow")
        self.assertNotContains(response, "fast")
        self.assertContains(response, "Показаны отчёты: 1")

    def test_class_breakdown_is_a_separate_colored_block(self):
        self._report("fast")
        self._report("second")
        self._report("slow", capacity=4000, rpm=5400, smr=True, verdict=Report.Verdict.UNPLAYABLE)

        response = self.client.get(reverse("game_detail", args=["steam", "200"]))

        html = response.content.decode()
        summary_end = html.index("</section>")
        classes = html.index("classes-panel")
        reports = html.index('class="panel reports-panel"')
        self.assertLess(summary_end, classes)
        self.assertLess(classes, reports)
        self.assertContains(response, "class-row--playable")
        self.assertContains(response, "class-row--unplayable")

    def test_my_configuration_link_uses_primary_drive(self):
        user = User.objects.create_user(username="owner", password="pass12345")
        UserDrive.objects.create(
            user=user, name="Other", capacity_gb=4000, rpm=5400, profile=profile_for(rpm=5400)
        )
        UserDrive.objects.create(
            user=user,
            name="Main",
            capacity_gb=2000,
            rpm=7200,
            smr=False,
            profile=profile_for(rpm=7200),
            is_primary=True,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("game_detail", args=["steam", "200"]))

        self.assertNotContains(response, "capacity=2000")
        self.assertContains(response, "rpm=7200")
        self.assertContains(response, "recording=cmr")

    def test_size_uses_median_of_fresh_reports(self):
        self._report("a", size=100)
        self._report("b", size=120)
        self._report("stale", size=400, days_ago=stats.SIZE_FRESH_DAYS + 1)

        size = stats.size_summary(self.game)

        self.assertEqual(size.community_gb, 110.0)
        self.assertEqual(size.reports, 2)
        self.assertEqual(size.stale_reports, 1)

    def test_size_falls_back_to_last_known_value(self):
        """Без свежих замеров остаётся последний известный размер и его дата."""
        self._report("old", size=90, days_ago=stats.SIZE_FRESH_DAYS + 40)
        self._report("older", size=80, days_ago=stats.SIZE_FRESH_DAYS + 200)

        size = stats.size_summary(self.game)

        self.assertEqual(size.community_gb, 90)
        self.assertEqual(size.reports, 0)
        self.assertEqual(size.stale_reports, 2)
        self.assertIsNotNone(size.latest)

    def test_stale_size_is_shown_on_the_page(self):
        self._report("old", size=90, days_ago=stats.SIZE_FRESH_DAYS + 40)

        response = self.client.get(reverse("game_detail", args=["steam", "200"]))

        self.assertContains(response, "По отчётам: ~90 ГБ")
        self.assertContains(response, "обновлено")

    def test_game_head_has_clamped_description_and_facts(self):
        """Описание ограничено по высоте, требования и размер — в полосе фактов."""
        self.game.short_description = "Длинное описание. " * 40
        self.game.save(update_fields=["short_description"])

        response = self.client.get(reverse("game_detail", args=["steam", "200"]))

        self.assertContains(response, 'class="game-description"')
        self.assertContains(response, "data-description-toggle")
        self.assertContains(response, 'class="facts"')
        self.assertContains(response, "Требования")

    def test_size_without_reports_is_empty(self):
        game = Game.objects.create(
            source=Game.Source.STEAM, external_id="201", title="No Size"
        )
        size = stats.size_summary(game)
        self.assertIsNone(size.community_gb)
        self.assertFalse(size.has_any)

    def test_size_without_reports_says_so_and_skips_store_size(self):
        """Размер магазина уже есть в требованиях — в «Размере игры» его нет."""
        response = self.client.get(reverse("game_detail", args=["steam", "200"]))
        self.assertContains(response, "Пока нет отчётов с размером игры")
        self.assertNotContains(response, "Steam: 70 ГБ")

    def test_verdict_breakdown_counts_reports(self):
        self._report("p1", verdict=Report.Verdict.PLAYABLE)
        self._report("l1", verdict=Report.Verdict.LIMITED)
        self._report("l2", verdict=Report.Verdict.LIMITED)

        mix = {row.key: row for row in stats.verdict_breakdown(self.game)}

        self.assertEqual(mix["playable"].count, 1)
        self.assertEqual(mix["limited"].count, 2)
        self.assertEqual(mix["unplayable"].count, 0)
        self.assertEqual(mix["playable"].percent, 33)
        self.assertEqual(mix["limited"].percent, 67)

    def test_drive_prediction_uses_reports_of_same_class(self):
        self._report("fast1", rpm=7200, smr=False)
        self._report("fast2", rpm=7200, smr=False)
        self._report("slow", rpm=5400, smr=True, verdict=Report.Verdict.UNPLAYABLE)
        drive = UserDrive.objects.get(user__username="fast1")

        prediction = stats.drive_prediction(self.game, drive)

        self.assertEqual(prediction.level, stats.LEVEL_PLAYABLE)
        self.assertEqual(prediction.reports, 2)
        self.assertEqual(prediction.drive_specs, "2 ТБ · 7200 об/мин · CMR")

    def test_drive_prediction_without_class_reports(self):
        user = User.objects.create_user(username="u1", password="pass12345")
        drive = UserDrive.objects.create(
            user=user,
            name="Fast",
            rpm=7200,
            smr=False,
            profile=profile_for(rpm=7200, smr=False),
        )

        prediction = stats.drive_prediction(self.game, drive)

        self.assertEqual(prediction.level, stats.LEVEL_NO_DATA)
        self.assertEqual(prediction.reports, 0)

    def test_drive_without_specs_has_no_prediction(self):
        user = User.objects.create_user(username="u1", password="pass12345")
        drive = UserDrive.objects.create(user=user, name="Unknown")

        self.assertIsNone(stats.drive_prediction(self.game, drive))

    def test_size_date_is_kept_when_size_does_not_change(self):
        user = User.objects.create_user(username="u1", password="pass12345")
        drive = UserDrive.objects.create(user=user, name="Drive", rpm=7200)
        report = save_report(
            game=self.game,
            user=user,
            user_drive=drive,
            verdict=Report.Verdict.PLAYABLE,
            install_size_gb=100,
        )
        first_date = report.install_size_updated
        self.assertIsNotNone(first_date)

        report = save_report(
            game=self.game,
            user=user,
            user_drive=drive,
            verdict=Report.Verdict.LIMITED,
            install_size_gb=100,
            comment="changed opinion",
        )
        report.refresh_from_db()
        self.assertEqual(report.install_size_updated, first_date)

        report = save_report(
            game=self.game,
            user=user,
            user_drive=drive,
            verdict=Report.Verdict.LIMITED,
            install_size_gb=120,
        )
        report.refresh_from_db()
        self.assertGreater(report.install_size_updated, first_date)

    def test_report_page_shows_community_size_and_stale_warning(self):
        self._report("a", size=100)
        self._report("stale", size=400, days_ago=stats.SIZE_FRESH_DAYS + 1)

        response = self.client.get(reverse("game_detail", args=["steam", "200"]))

        self.assertContains(response, "По отчётам: ~100")
        self.assertNotContains(response, "Steam: 70")
        self.assertContains(response, "Данные о размере устарели")


class _FakeHTTPResponse:
    """Минимальный ответ urllib для тестов DeepL."""

    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _FakeTextResponse:
    """Ответ urllib с простым текстом — для проверки OpenID."""

    def __init__(self, text: str):
        self._body = text.encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@override_settings(DEEPL_API_KEY="")
class CommentTranslationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="author", password="pass12345")
        cls.game = Game.objects.create(
            source=Game.Source.STEAM, external_id="300", title="Comment Game"
        )
        cls.report = Report.objects.create(
            game=cls.game,
            user=cls.user,
            verdict=Report.Verdict.PLAYABLE,
            comment="Игра идёт с фризами",
        )

    def _url(self) -> str:
        return reverse("translate_comment", args=[self.report.pk])

    def test_button_is_hidden_without_api_key(self):
        response = self.client.get(reverse("game_detail", args=["steam", "300"]))
        self.assertContains(response, "Игра идёт с фризами")
        self.assertNotContains(response, self._url())

    @override_settings(DEEPL_API_KEY="test-key:fx")
    def test_button_is_shown_with_api_key(self):
        response = self.client.get(reverse("game_detail", args=["steam", "300"]))
        self.assertContains(response, self._url())
        self.assertContains(response, "Перевести")

    @override_settings(DEEPL_API_KEY="test-key:fx")
    @patch("games.services.translate.urllib.request.urlopen")
    def test_translation_is_stored_and_reused(self, urlopen):
        urlopen.return_value = _FakeHTTPResponse(
            {"translations": [{"text": "The game stutters"}]}
        )

        response = self.client.post(self._url(), {"next": "/game/steam/300/"})

        self.assertEqual(response.status_code, 302)
        self.assertIn("translated=", response.url)
        translation = CommentTranslation.objects.get(
            report=self.report, language="ru"
        )
        self.assertEqual(translation.text, "The game stutters")
        self.assertIn("target_lang=RU", urlopen.call_args.args[0].data.decode())
        self.assertTrue(urlopen.call_args.args[0].full_url.startswith("https://api-free."))

        # Повторный клик берёт готовый перевод из базы.
        self.client.post(self._url(), {"next": "/game/steam/300/"})
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(
            CommentTranslation.objects.filter(report=self.report).count(), 1
        )

    @override_settings(DEEPL_API_KEY="test-key:fx")
    @patch("games.services.translate.urllib.request.urlopen")
    def test_translated_comment_is_shown_and_can_be_opened(self, urlopen):
        urlopen.return_value = _FakeHTTPResponse(
            {"translations": [{"text": "The game stutters"}]}
        )
        self.client.post(self._url(), {"next": "/game/steam/300/"})

        response = self.client.get(
            reverse("game_detail", args=["steam", "300"]),
            {"translated": self.report.pk},
        )

        self.assertContains(response, "The game stutters")
        self.assertContains(response, "Машинный перевод")
        self.assertContains(response, 'class="report-translation" open')

    @override_settings(DEEPL_API_KEY="test-key:fx")
    @patch("games.services.translate.urllib.request.urlopen")
    def test_target_language_follows_interface(self, urlopen):
        urlopen.return_value = _FakeHTTPResponse(
            {"translations": [{"text": "Гра йде з фризами"}]}
        )
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "uk"

        self.client.post(self._url(), {"next": "/game/steam/300/"})

        self.assertIn("target_lang=UK", urlopen.call_args.args[0].data.decode())
        self.assertTrue(
            CommentTranslation.objects.filter(
                report=self.report, language="uk"
            ).exists()
        )

    @override_settings(DEEPL_API_KEY="test-key:fx")
    @patch("games.services.translate.urllib.request.urlopen")
    def test_failed_translation_shows_error_without_saving(self, urlopen):
        urlopen.side_effect = urllib.error.URLError("boom")

        response = self.client.post(
            self._url(), {"next": "/game/steam/300/"}, follow=True
        )

        self.assertContains(response, "Не удалось перевести комментарий")
        self.assertFalse(CommentTranslation.objects.exists())

    def test_translation_without_key_reports_error(self):
        response = self.client.post(
            self._url(), {"next": "/game/steam/300/"}, follow=True
        )
        self.assertContains(response, "Перевод комментариев не настроен")
        self.assertFalse(CommentTranslation.objects.exists())

    @override_settings(DEEPL_API_KEY="test-key:fx")
    @patch("games.services.translate.urllib.request.urlopen")
    def test_external_next_is_ignored(self, urlopen):
        urlopen.return_value = _FakeHTTPResponse(
            {"translations": [{"text": "Translated"}]}
        )
        response = self.client.post(self._url(), {"next": "https://evil.example/"})
        self.assertIn("/game/steam/300/", response.url)
        self.assertNotIn("evil.example", response.url)

    def test_pro_key_uses_pro_endpoint(self):
        with override_settings(DEEPL_API_KEY="test-key"):
            self.assertTrue(
                comment_translate._endpoint().startswith("https://api.deepl.com")
            )
        with override_settings(DEEPL_API_KEY="test-key:fx"):
            self.assertTrue(
                comment_translate._endpoint().startswith("https://api-free.deepl.com")
            )

    def test_hidden_report_cannot_be_translated(self):
        self.report.hidden = True
        self.report.save(update_fields=["hidden"])
        response = self.client.post(self._url(), {"next": "/game/steam/300/"})
        self.assertEqual(response.status_code, 404)

    def test_editing_comment_drops_stale_translations(self):
        CommentTranslation.objects.create(
            report=self.report, language="ru", text="The game stutters"
        )

        save_report(
            game=self.game,
            user=self.user,
            user_drive=None,
            verdict=Report.Verdict.PLAYABLE,
            comment="Новый комментарий",
        )

        self.assertFalse(
            CommentTranslation.objects.filter(report=self.report).exists()
        )

    def test_saving_report_without_comment_change_keeps_translations(self):
        CommentTranslation.objects.create(
            report=self.report, language="ru", text="The game stutters"
        )

        save_report(
            game=self.game,
            user=self.user,
            user_drive=None,
            verdict=Report.Verdict.LIMITED,
            comment="Игра идёт с фризами",
        )

        self.assertTrue(
            CommentTranslation.objects.filter(report=self.report).exists()
        )


class LocalizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.game = Game.objects.create(
            source=Game.Source.STEAM,
            external_id="292030",
            title="The Witcher 3: Wild Hunt",
            title_en="The Witcher 3: Wild Hunt",
            title_ru="Ведьмак 3: Дикая Охота",
            title_uk="Відьмак 3: Дикий гін",
            genre="RPG",
            genre_en="RPG",
            genre_ru="Ролевая игра",
            genre_uk="Рольові ігри",
            short_description="Description",
            short_description_en="Description",
            short_description_ru="Описание",
            short_description_uk="Опис",
            cover_url="https://cdn.example/292030/capsule_616x353.jpg",
            cover_url_ru="https://cdn.example/292030/capsule_616x353_russian.jpg",
            cover_url_uk="https://cdn.example/292030/capsule_616x353_ukrainian.jpg",
            store_url="https://store.steampowered.com/app/292030/",
        )

    def test_game_fields_follow_language(self):
        with translation.override("en"):
            self.assertEqual(self.game.display_title, "The Witcher 3: Wild Hunt")
            self.assertEqual(self.game.display_genre, "RPG")
            self.assertEqual(self.game.display_description, "Description")
            self.assertEqual(
                self.game.cover_url_display,
                "https://cdn.example/292030/capsule_616x353.jpg",
            )
            self.assertIn("l=english", self.game.store_url_display)

        with translation.override("uk"):
            self.assertEqual(self.game.display_title, "Відьмак 3: Дикий гін")
            self.assertEqual(self.game.display_genre, "Рольові ігри")
            self.assertEqual(self.game.display_description, "Опис")
            self.assertEqual(
                self.game.cover_url_display,
                "https://cdn.example/292030/capsule_616x353_ukrainian.jpg",
            )
            self.assertIn("l=ukrainian", self.game.store_url_display)

        with translation.override("ru"):
            self.assertEqual(self.game.display_title, "Ведьмак 3: Дикая Охота")
            self.assertEqual(self.game.display_genre, "Ролевая игра")
            self.assertEqual(self.game.display_description, "Описание")
            self.assertEqual(
                self.game.cover_url_display,
                "https://cdn.example/292030/capsule_616x353_russian.jpg",
            )
            self.assertIn("l=russian", self.game.store_url_display)

    def test_report_counts_use_plural_forms(self):
        with translation.override("ru"):
            self.assertEqual(translate_plural("game.reports_count", 1), "1 отчёт")
            self.assertEqual(translate_plural("game.reports_count", 3), "3 отчёта")
            self.assertEqual(translate_plural("game.reports_count", 11), "11 отчётов")
            self.assertEqual(translate_plural("game.reports_count", 21), "21 отчёт")
        with translation.override("en"):
            self.assertEqual(translate_plural("game.reports_count", 1), "1 report")
            self.assertEqual(translate_plural("game.reports_count", 3), "3 reports")

    def test_russian_cover_falls_back_to_base(self):
        game = Game.objects.create(
            source=Game.Source.STEAM,
            external_id="730",
            title="Counter-Strike 2",
            cover_url="https://cdn.example/730/capsule_616x353.jpg",
        )
        with translation.override("ru"):
            self.assertEqual(
                game.cover_url_display, "https://cdn.example/730/capsule_616x353.jpg"
            )
            self.assertTrue(
                game.cover_fallback_url.endswith("/730/header_russian.jpg")
            )

    def test_english_fields_fall_back_to_russian(self):
        game = Game.objects.create(
            source=Game.Source.STEAM, external_id="1", title="Только русский"
        )
        with translation.override("en"):
            self.assertEqual(game.display_title, "Только русский")

    def test_language_switch_changes_interface(self):
        response = self.client.post(
            reverse("set_language"), {"language": "en", "next": "/"}
        )
        self.assertEqual(response.status_code, 302)

        response = self.client.get(reverse("home"))
        self.assertContains(response, "Will the game run on your hard drive?")
        self.assertNotContains(response, "Пойдёт ли игра")

        response = self.client.post(
            reverse("set_language"), {"language": "ru", "next": "/"}
        )
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Пойдёт ли игра")

    def test_language_switch_is_shown_in_header(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "lang-menu")
        self.assertContains(response, 'value="ru"')
        self.assertContains(response, 'value="en"')
        self.assertContains(response, 'value="uk"')
        self.assertContains(response, "Українська")

    def test_ukrainian_switch_changes_interface(self):
        self.addCleanup(translation.deactivate)
        response = self.client.post(
            reverse("set_language"), {"language": "uk", "next": "/"}
        )
        self.assertEqual(response.status_code, 302)

        response = self.client.get(reverse("home"))
        self.assertContains(response, "Чи піде гра на вашому жорсткому диску?")
        self.assertNotContains(response, "Пойдёт ли игра")

    def test_ukrainian_translates_every_key(self):
        from games.i18n import TRANSLATIONS, UKRAINIAN

        missing = sorted(set(TRANSLATIONS) - set(UKRAINIAN))
        extra = sorted(set(UKRAINIAN) - set(TRANSLATIONS))
        self.assertEqual(missing, [])
        self.assertEqual(extra, [])

    def test_ukrainian_game_fields_fall_back_to_english(self):
        game = Game.objects.create(
            source=Game.Source.STEAM,
            external_id="730",
            title="Контра-Страйк 2",
            title_en="Counter-Strike 2",
            genre="Шутер",
            genre_en="Shooter",
            short_description="Описание",
            short_description_en="Description",
            cover_url="https://cdn.example/730/capsule_616x353.jpg",
        )
        with translation.override("uk"):
            self.assertEqual(game.display_title, "Counter-Strike 2")
            self.assertEqual(game.display_genre, "Shooter")
            self.assertEqual(game.display_description, "Description")
            self.assertIn("l=ukrainian", game.store_url_display)
            self.assertTrue(game.cover_fallback_url.endswith("/730/header.jpg"))

    def test_ukrainian_plural_forms(self):
        with translation.override("uk"):
            self.assertEqual(translate_plural("game.reports_count", 1), "1 звіт")
            self.assertEqual(translate_plural("game.reports_count", 3), "3 звіти")
            self.assertEqual(translate_plural("game.reports_count", 11), "11 звітів")
            self.assertEqual(translate_plural("game.reports_count", 21), "21 звіт")


class SteamParsingTests(TestCase):
    def test_game_payload_extracts_storage_and_ssd(self):
        details = {
            "name": "Example",
            "genres": [{"description": "RPG"}],
            "release_date": {"date": "19 May, 2015"},
            "header_image": "https://example.com/header.jpg",
            "short_description": "Desc",
            "pc_requirements": {
                "minimum": "<strong>Storage:</strong> 50 GB available space",
                "recommended": "<li><strong>Storage:</strong> 70 GB <b>SSD</b> required</li>",
            },
        }

        payload = steam.payload_from_details(details, 42, "Example English")

        self.assertEqual(payload["source"], "steam")
        self.assertEqual(payload["external_id"], "42")
        self.assertEqual(payload["title_en"], "Example English")
        self.assertEqual(payload["genre"], "RPG")
        self.assertEqual(payload["release_year"], 2015)
        self.assertEqual(payload["storage_gb"], 70)
        self.assertTrue(payload["requires_ssd"])
        self.assertIn("/app/42/", payload["store_url"])

    def test_game_payload_without_requirements(self):
        payload = steam.payload_from_details({"name": "Empty"}, 7)
        self.assertIsNone(payload["storage_gb"])
        self.assertIsNone(payload["requires_ssd"])
        self.assertEqual(payload["title_en"], "")

    def test_game_payload_keeps_english_title(self):
        payload = steam.payload_from_details({"name": "Same"}, 7, "Same")
        self.assertEqual(payload["title_en"], "Same")

    def test_game_payload_uses_ukrainian_locale(self):
        details = {"name": "The Witcher 3", "genres": [{"description": "RPG"}]}
        ukrainian = {
            "name": "Відьмак 3",
            "genres": [{"description": "Рольові ігри"}],
            "short_description": "Опис українською",
        }
        payload = steam.payload_from_details(
            details, 292030, "The Witcher 3", ukrainian_details=ukrainian
        )
        self.assertEqual(payload["title"], "The Witcher 3")
        self.assertEqual(payload["title_uk"], "Відьмак 3")
        self.assertEqual(payload["genre_uk"], "Рольові ігри")
        self.assertEqual(payload["short_description_uk"], "Опис українською")

    def test_game_payload_uses_russian_locale(self):
        details = {"name": "The Witcher 3", "genres": [{"description": "RPG"}]}
        russian = {
            "name": "Ведьмак 3",
            "genres": [{"description": "Ролевые игры"}],
            "short_description": "Описание по-русски",
        }
        payload = steam.payload_from_details(
            details, 292030, "The Witcher 3", russian_details=russian
        )
        self.assertEqual(payload["title"], "The Witcher 3")
        self.assertEqual(payload["title_ru"], "Ведьмак 3")
        self.assertEqual(payload["genre_ru"], "Ролевые игры")
        self.assertEqual(payload["short_description_ru"], "Описание по-русски")

    def test_game_payload_without_localized_fields_leaves_them_empty(self):
        payload = steam.payload_from_details({"name": "Same"}, 7)
        self.assertEqual(payload["title_ru"], "")
        self.assertEqual(payload["genre_ru"], "")
        self.assertEqual(payload["short_description_ru"], "")
        self.assertEqual(payload["title_uk"], "")
        self.assertEqual(payload["genre_uk"], "")
        self.assertEqual(payload["short_description_uk"], "")

    def test_storage_ignores_ram_and_handles_ssd_inside_line(self):
        markup = (
            "<li><strong>ОЗУ:</strong> 12 GB</li>"
            "<li><strong>Видеокарта:</strong> GTX 1660 8GB</li>"
            "<li><strong>Место на диске:</strong> 60 SSD GB</li>"
        )
        self.assertEqual(storage_gb(markup), 60.0)

    def test_storage_without_storage_line_uses_max(self):
        markup = "<li><strong>ОЗУ:</strong> 16 GB</li><li>Дополнительно: 25 GB</li>"
        self.assertEqual(storage_gb(markup), 25.0)

    def test_requires_ssd(self):
        self.assertTrue(requires_ssd("Storage: 90 GB SSD required"))
        self.assertFalse(requires_ssd("Storage: 90 GB available space"))
        self.assertIsNone(requires_ssd(""))

    @patch("games.services.steam._get_json")
    def test_search_requests_games_only(self, get_json):
        get_json.return_value = {"success": 1, "results_html": ""}

        steam.search_games("hdd-verified-test-term")

        url = get_json.call_args.args[0]
        self.assertIn("category1=998", url)
        self.assertIn("json=1", url)

    def test_search_rows_use_large_cover_with_fallback(self):
        markup = (
            '<a href="/app/10/" data-ds-appid="10">'
            '<div class="search_capsule"><img src="https://cdn/capsule_231x87.jpg"></div>'
            '<div class="search_name"><span class="title">Game &amp; Sound</span></div></a>'
            '<a href="/app/11/" data-ds-appid="11">'
            '<div class="search_name"><span class="title">No Capsule</span></div></a>'
        )

        with translation.override("en"):
            results = steam._parse_search_rows(markup, "english")

        self.assertEqual([item.external_id for item in results], ["10", "11"])
        self.assertEqual([item.source for item in results], ["steam", "steam"])
        self.assertEqual(results[0].name, "Game & Sound")
        self.assertTrue(results[0].image.endswith("/10/header.jpg"))
        self.assertEqual(results[0].fallback_image, "https://cdn/capsule_231x87.jpg")
        self.assertEqual(results[1].fallback_image, "https://cdn.cloudflare.steamstatic.com/steam/apps/11/header.jpg")

    def test_search_rows_use_russian_cover(self):
        markup = (
            '<a href="/app/10/" data-ds-appid="10">'
            '<span class="title">Ведьмак</span></a>'
        )

        with translation.override("ru"):
            results = steam._parse_search_rows(markup, "russian")

        self.assertTrue(results[0].image.endswith("/10/header_russian.jpg"))

    def test_header_image_depends_on_language(self):
        with translation.override("ru"):
            self.assertTrue(steam.header_image(10).endswith("/10/header_russian.jpg"))
        with translation.override("en"):
            self.assertTrue(steam.header_image(10).endswith("/10/header.jpg"))
        self.assertTrue(steam.header_image(10, "russian").endswith("/header_russian.jpg"))

    @patch("games.services.steam._get_html")
    def test_store_capsule_reads_hashed_cover_from_store_page(self, get_html):
        cache.clear()
        get_html.return_value = (
            '<img src="https://shared.fastly.steamstatic.com/store_item_assets/'
            'steam/apps/999/aaa/capsule_616x353.jpg?t=1">'
            '<img src="https://shared.fastly.steamstatic.com/store_item_assets/'
            'steam/apps/730/bbb/capsule_616x353_alt_assets_2.jpg?t=2">'
        )

        capsule = steam.store_capsule(730, "english")

        self.assertEqual(
            capsule,
            "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/730/"
            "bbb/capsule_616x353_alt_assets_2.jpg?t=2",
        )

    @patch("games.services.steam._get_html")
    def test_store_capsule_is_empty_without_cover(self, get_html):
        cache.clear()
        get_html.return_value = "<html><body>Возрастное ограничение</body></html>"

        self.assertEqual(steam.store_capsule(292030, "russian"), "")

    def test_search_rows_are_deduplicated(self):
        row = (
            '<a href="/app/10/" data-ds-appid="10">'
            '<span class="title">Same</span></a>'
        )
        self.assertEqual(len(steam._parse_search_rows(row + row)), 1)


class CatalogTests(TestCase):
    def test_normalize_title_ignores_punctuation_and_edition(self):
        self.assertEqual(
            normalize_title("The Witcher 3: Wild Hunt — Remastered"),
            normalize_title("The Witcher 3 - Wild Hunt"),
        )
        self.assertEqual(
            normalize_title("Ведьмак 3: Дикая Охота — Обновлённое издание"),
            normalize_title("Ведьмак 3: Дикая Охота"),
        )

    def test_normalize_title_keeps_sequels_apart(self):
        self.assertNotEqual(normalize_title("Dark Souls"), normalize_title("Dark Souls II"))

    def test_normalize_title_strips_russian_edition(self):
        self.assertEqual(
            normalize_title("Alan Wake 2: делюкс-издание"),
            normalize_title("Alan Wake 2"),
        )

    @patch("games.services.search.epic.search_games")
    @patch("games.services.search.steam.search_games")
    def test_exact_match_beats_irrelevant_steam_results(self, steam_search, epic_search):
        steam_search.return_value = [
            SearchResult("steam", "1", "Aim Trainer", ""),
            SearchResult("steam", "2", "Aim Hero", ""),
        ]
        epic_search.return_value = [SearchResult("epic", "fn:1", "Fortnite", "")]

        results = game_search.search_games("fortnite")

        self.assertEqual(results[0].name, "Fortnite")
        self.assertEqual(results[0].source, "epic")

    @patch("games.services.search.epic.search_games")
    @patch("games.services.search.steam.search_games")
    def test_steam_wins_when_stores_have_same_game(self, steam_search, epic_search):
        steam_search.return_value = [
            SearchResult("steam", "292030", "Ведьмак 3: Дикая Охота", "")
        ]
        epic_search.return_value = [
            SearchResult(
                "epic", "ns:id", "Ведьмак 3: Дикая Охота — Обновлённое издание", ""
            )
        ]

        results = game_search.search_games("witcher")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].source, "steam")

    @patch("games.services.search.epic.search_games")
    @patch("games.services.search.steam.search_games")
    def test_search_survives_one_store_failure(self, steam_search, epic_search):
        steam_search.side_effect = steam.SteamError("down")
        epic_search.return_value = [SearchResult("epic", "ns:id", "Exclusive", "")]

        results = game_search.search_games("exclusive")

        self.assertEqual([item.source for item in results], ["epic"])

    @patch("games.services.search.epic.search_games")
    @patch("games.services.search.steam.search_games")
    def test_search_reports_error_when_both_stores_fail(self, steam_search, epic_search):
        steam_search.side_effect = steam.SteamError("steam down")
        epic_search.side_effect = epic.EpicError("epic down")

        with self.assertRaises(game_search.SearchError):
            game_search.search_games("anything")


class EpicParsingTests(TestCase):
    #: Ответ контентного API Epic с требованиями к накопителю.
    requirements_payload = {
        "pages": [
            {
                "data": {
                    "requirements": {
                        "systems": [
                            {
                                "systemType": "Windows",
                                "details": [
                                    {"title": "Windows Memory", "minimum": "16 GB"},
                                    {
                                        "title": "Windows Storage",
                                        "minimum": "SSD with 90 GB free space",
                                    },
                                ],
                            }
                        ]
                    }
                }
            }
        ]
    }

    def setUp(self):
        cache.clear()

    @patch("games.services.epic._get_json")
    @patch("games.services.epic._post")
    def test_game_payload_uses_english_and_russian_locales(self, post, get_json):
        get_json.return_value = self.requirements_payload
        post.side_effect = [
            {
                "data": {
                    "Catalog": {
                        "catalogOffer": {
                            "title": "The Witcher 3: Wild Hunt",
                            "description": "<p>Description</p>",
                            "releaseDate": "2015-05-18T00:00:00.000Z",
                            "urlSlug": "the-witcher-3",
                            "productSlug": "the-witcher-3-wild-hunt",
                            "keyImages": [
                                {"type": "Thumbnail", "url": "https://cdn/thumb.jpg"},
                                {"type": "OfferImageWide", "url": "https://cdn/wide.jpg"},
                            ],
                        }
                    }
                }
            },
            {
                "data": {
                    "Catalog": {
                        "catalogOffer": {
                            "title": "Ведьмак 3: Дикая Охота",
                            "description": "<p>Описание</p>",
                            "releaseDate": "2015-05-18T00:00:00.000Z",
                            "urlSlug": "the-witcher-3",
                            "productSlug": "the-witcher-3-wild-hunt",
                            "keyImages": [],
                        }
                    }
                }
            },
        ]

        payload = epic.game_payload("ns:offer")

        self.assertEqual(payload["source"], "epic")
        self.assertEqual(payload["external_id"], "ns:offer")
        self.assertEqual(payload["title"], "The Witcher 3: Wild Hunt")
        self.assertEqual(payload["title_en"], "The Witcher 3: Wild Hunt")
        self.assertEqual(payload["title_ru"], "Ведьмак 3: Дикая Охота")
        self.assertEqual(payload["cover_url"], "https://cdn/wide.jpg")
        self.assertEqual(payload["short_description"], "Description")
        self.assertEqual(payload["short_description_ru"], "Описание")
        self.assertEqual(payload["release_year"], 2015)
        self.assertIn("/en-US/p/the-witcher-3-wild-hunt", payload["store_url"])
        self.assertEqual(payload["storage_gb"], 90.0)
        self.assertTrue(payload["requires_ssd"])

    @patch("games.services.epic._get_json")
    def test_requirements_from_content_api(self, get_json):
        get_json.return_value = self.requirements_payload

        requirements = epic.fetch_requirements("alan-wake-2")

        self.assertEqual(requirements.storage_gb, 90.0)
        self.assertTrue(requirements.requires_ssd)
        self.assertIn("content/products/alan-wake-2", get_json.call_args.args[0])

    @patch("games.services.epic._get_json")
    def test_requirements_without_storage_are_empty(self, get_json):
        get_json.return_value = {"pages": []}

        requirements = epic.fetch_requirements("without-requirements")

        self.assertIsNone(requirements.storage_gb)
        self.assertIsNone(requirements.requires_ssd)

    @patch("games.services.epic._get_json")
    def test_requirements_error_does_not_break_import(self, get_json):
        get_json.side_effect = epic.EpicError("down")

        requirements = epic.fetch_requirements("unreachable")

        self.assertIsNone(requirements.storage_gb)
        self.assertIsNone(requirements.requires_ssd)

    def test_external_id_validation(self):
        self.assertTrue(epic.is_valid_external_id("abc123:def456"))
        self.assertFalse(epic.is_valid_external_id("abc123"))
        self.assertFalse(epic.is_valid_external_id("abc/def:ghi"))


class ViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.game = Game.objects.create(
            source=Game.Source.STEAM, external_id="100", title="Known Game"
        )

    def test_home_page(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "HDD Verified")

    @patch("games.views.get_or_create_game")
    def test_game_detail_page(self, get_game):
        get_game.return_value = self.game
        response = self.client.get(reverse("game_detail", args=["steam", "100"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Known Game")
        self.assertContains(response, "Войдите")
        self.assertContains(response, "На вашем диске")
        self.assertContains(response, "чтобы увидеть прогноз")

    @patch("games.views.get_or_create_game")
    def test_legacy_url_redirects_to_canonical(self, get_game):
        get_game.return_value = self.game
        response = self.client.get("/game/100/")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, "/game/steam/100/")

    def test_unknown_store_is_not_found(self):
        response = self.client.get("/game/gog/100/")
        self.assertEqual(response.status_code, 404)

    def test_report_requires_login(self):
        response = self.client.post(
            reverse("submit_report", args=["steam", "100"]), {"verdict": "playable"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def _report_for(self, username: str) -> tuple[User, Report]:
        user = User.objects.create_user(username=username, password="pass12345")
        report = Report.objects.create(
            game=self.game, user=user, verdict=Report.Verdict.PLAYABLE
        )
        return user, report

    def test_delete_report_removes_own_report(self):
        user, report = self._report_for("owner")
        self.client.force_login(user)

        response = self.client.post(reverse("delete_report", args=[report.pk]))

        self.assertRedirects(
            response, self.game.get_absolute_url(), fetch_redirect_response=False
        )
        self.assertFalse(Report.objects.filter(pk=report.pk).exists())

    def test_delete_report_requires_login(self):
        _, report = self._report_for("owner")

        response = self.client.post(reverse("delete_report", args=[report.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.assertTrue(Report.objects.filter(pk=report.pk).exists())

    def test_cannot_delete_another_users_report(self):
        _, report = self._report_for("owner")
        other = User.objects.create_user(username="other", password="pass12345")
        self.client.force_login(other)

        response = self.client.post(reverse("delete_report", args=[report.pk]))

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Report.objects.filter(pk=report.pk).exists())

    def test_edit_form_has_delete_button(self):
        user, report = self._report_for("owner")
        self.client.force_login(user)

        response = self.client.get(reverse("game_detail", args=["steam", "100"]))

        self.assertContains(response, reverse("delete_report", args=[report.pk]))
        self.assertContains(response, "Удалить оценку")

    def test_create_form_has_no_delete_button(self):
        user = User.objects.create_user(username="newbie", password="pass12345")
        self.client.force_login(user)

        response = self.client.get(reverse("game_detail", args=["steam", "100"]))

        self.assertNotContains(response, "Удалить оценку")

    def test_report_without_drive(self):
        user = User.objects.create_user(username="u1", password="pass12345")
        self.client.force_login(user)

        response = self.client.post(
            reverse("submit_report", args=["steam", "100"]),
            {
                "verdict": Report.Verdict.PLAYABLE,
                "stutter": "",
                "load_speed": Report.LoadSpeed.SLOW,
                "comment": "ok",
            },
        )

        self.assertEqual(response.status_code, 302)
        report = Report.objects.get(game=self.game, user=user)
        self.assertEqual(report.drive_name, "")
        self.assertIsNone(report.profile)
        self.assertEqual(report.load_speed, Report.LoadSpeed.SLOW)

    def test_invalid_report_reopens_dialog(self):
        user = User.objects.create_user(username="u1", password="pass12345")
        self.client.force_login(user)

        response = self.client.post(
            reverse("submit_report", args=["steam", "100"]),
            {"verdict": "", "stutter": "", "load_speed": "", "comment": "x"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["report_form_open"])
        self.assertContains(response, "report-dialog")
        self.assertContains(response, "Обязательное поле")

    @patch("games.views.get_or_create_game")
    def test_report_dialog_is_closed_on_page_load(self, get_game):
        get_game.return_value = self.game
        user = User.objects.create_user(username="u1", password="pass12345")
        self.client.force_login(user)

        response = self.client.get(reverse("game_detail", args=["steam", "100"]))

        self.assertFalse(response.context["report_form_open"])
        self.assertContains(response, "report-dialog")
        self.assertContains(response, "Оценить игру")

    @patch("games.views.get_or_create_game")
    def test_report_form_hints_are_tooltips(self, get_game):
        """Подсказки к полям — знак вопроса, а не текст под контролом."""
        get_game.return_value = self.game
        user = User.objects.create_user(username="u1", password="pass12345")
        self.client.force_login(user)

        response = self.client.get(reverse("game_detail", args=["steam", "100"]))

        html = response.content.decode()
        dialog_html = html.split('id="report-dialog"', 1)[1]
        self.assertEqual(dialog_html.count('class="hint"'), 4)
        filter_html = html.split('class="form filter"', 1)[1].split("</form>", 1)[0]
        self.assertEqual(filter_html.count('class="hint"'), 2)
        self.assertContains(response, "Проверьте размер папки игры")
        self.assertContains(response, "Чем выше, тем быстрее игра грузится")

    @patch("games.views.get_or_create_game")
    def test_load_speed_options_show_only_periods(self, get_game):
        """В списке «Загрузка до меню» остаются только периоды."""
        get_game.return_value = self.game
        user = User.objects.create_user(username="u1", password="pass12345")
        self.client.force_login(user)

        response = self.client.get(reverse("game_detail", args=["steam", "100"]))

        for label in ("до 15 с", "15–60 с", "1–3 мин", "больше 3 мин"):
            self.assertContains(response, f">{label}<")
        self.assertNotContains(response, "Быстро — до 15 с")

    @patch("games.views.get_or_create_game")
    def test_prediction_hint_without_drive(self, get_game):
        get_game.return_value = self.game
        user = User.objects.create_user(username="u1", password="pass12345")
        self.client.force_login(user)

        response = self.client.get(reverse("game_detail", args=["steam", "100"]))

        self.assertIsNone(response.context["prediction"])
        self.assertContains(response, "Добавьте свой диск")
        self.assertContains(response, "чтобы увидеть прогноз для него")

    @patch("games.views.get_or_create_game")
    def test_prediction_hint_for_drive_without_specs(self, get_game):
        get_game.return_value = self.game
        user = User.objects.create_user(username="u1", password="pass12345")
        UserDrive.objects.create(user=user, name="Unknown drive")
        self.client.force_login(user)

        response = self.client.get(reverse("game_detail", args=["steam", "100"]))

        self.assertIsNone(response.context["prediction"])
        self.assertContains(response, "Укажите у диска обороты")

    def test_report_with_drive_saves_snapshot(self):
        user = User.objects.create_user(username="u1", password="pass12345")
        drive = UserDrive.objects.create(
            user=user,
            name="Seagate ST2000DM008",
            capacity_gb=2000,
            rpm=7200,
            smr=False,
            profile=profile_for(rpm=7200),
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("submit_report", args=["steam", "100"]),
            {
                "drive": drive.pk,
                "verdict": Report.Verdict.PLAYABLE,
                "stutter": "",
                "load_speed": "",
                "comment": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        report = Report.objects.get(game=self.game, user=user)
        self.assertEqual(report.drive_name, "Seagate ST2000DM008")
        self.assertEqual(report.drive_specs, "2 ТБ · 7200 об/мин · CMR")
        self.assertEqual(report.profile.slug, "hdd-7200-cmr")

    @patch("games.views.get_or_create_game")
    def test_game_page_shows_reported_drive(self, get_game):
        get_game.return_value = self.game
        user = User.objects.create_user(username="u1", password="pass12345")
        drive = UserDrive.objects.create(
            user=user,
            name="WD Blue WD20EZAZ",
            capacity_gb=2000,
            rpm=5400,
            smr=True,
            profile=profile_for(rpm=5400, smr=True),
        )
        save_report(
            game=self.game, user=user, user_drive=drive,
            verdict=Report.Verdict.LIMITED,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("game_detail", args=["steam", "100"]))

        self.assertContains(response, "WD Blue WD20EZAZ")
        self.assertContains(response, "2 ТБ · 5400 об/мин · SMR")
        self.assertContains(response, "На вашем диске")
        self.assertContains(response, "Скорее с оговорками")

    def test_my_drives_requires_login(self):
        response = self.client.get(reverse("my_drives"))
        self.assertEqual(response.status_code, 302)

    @patch("games.views.game_search.search_games")
    def test_game_search_api(self, search_games):
        search_games.return_value = [
            SearchResult(source="steam", external_id="1", name="A", image="")
        ]
        response = self.client.get(reverse("game_search_api"), {"q": "abc"})
        result = response.json()["results"][0]
        self.assertEqual(result["url"], "/game/steam/1/")
        self.assertEqual(result["source"], "steam")


class SteamAuthServiceTests(TestCase):
    """Проверка OpenID-ответа и публичного профиля Steam."""

    steam_id = "76561197960287930"
    return_to = "http://testserver/accounts/steam/callback/"

    def _params(self, **overrides):
        params = {
            "openid.mode": "id_res",
            "openid.return_to": self.return_to,
            "openid.claimed_id": (
                f"https://steamcommunity.com/openid/id/{self.steam_id}"
            ),
        }
        params.update(overrides)
        return params

    def test_login_url_has_openid_parameters(self):
        url = steam_auth.build_login_url(self.return_to, "http://testserver")
        parts = urllib.parse.urlsplit(url)
        query = dict(urllib.parse.parse_qsl(parts.query))

        self.assertEqual(f"{parts.scheme}://{parts.netloc}", "https://steamcommunity.com")
        self.assertEqual(query["openid.mode"], "checkid_setup")
        self.assertEqual(query["openid.return_to"], self.return_to)
        self.assertEqual(query["openid.realm"], "http://testserver")
        self.assertEqual(
            query["openid.claimed_id"],
            "http://specs.openid.net/auth/2.0/identifier_select",
        )

    @patch("games.services.steam_auth.urllib.request.urlopen")
    def test_verify_response_posts_back_and_returns_steam_id(self, urlopen):
        urlopen.return_value = _FakeTextResponse("ns:test\nis_valid:true\n")

        result = steam_auth.verify_response(self._params(), self.return_to)

        self.assertEqual(result, self.steam_id)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, steam_auth.OPENID_ENDPOINT)
        body = request.data.decode()
        self.assertIn("openid.mode=check_authentication", body)
        self.assertIn("openid.claimed_id=", body)

    @patch("games.services.steam_auth.urllib.request.urlopen")
    def test_verify_response_rejects_invalid_signature(self, urlopen):
        urlopen.return_value = _FakeTextResponse("is_valid:false\n")

        with self.assertRaises(steam_auth.SteamAuthError):
            steam_auth.verify_response(self._params(), self.return_to)

    def test_verify_response_rejects_foreign_return_to(self):
        with self.assertRaises(steam_auth.SteamAuthError):
            steam_auth.verify_response(
                self._params(**{"openid.return_to": "https://evil.example/"}),
                self.return_to,
            )

    @patch("games.services.steam_auth.urllib.request.urlopen")
    def test_verify_response_rejects_unknown_identity(self, urlopen):
        urlopen.return_value = _FakeTextResponse("is_valid:true\n")

        with self.assertRaises(steam_auth.SteamAuthError):
            steam_auth.verify_response(
                self._params(
                    **{"openid.claimed_id": "https://example.com/openid/id/1"}
                ),
                self.return_to,
            )

    @override_settings(STEAM_API_KEY="")
    def test_profile_without_api_key_is_empty(self):
        self.assertEqual(steam_auth.fetch_profile(self.steam_id), {})

    @override_settings(STEAM_API_KEY="test-key")
    @patch("games.services.steam_auth.urllib.request.urlopen")
    def test_profile_parses_public_data(self, urlopen):
        urlopen.return_value = _FakeTextResponse(
            json.dumps(
                {
                    "response": {
                        "players": [
                            {
                                "personaname": "Gabe",
                                "avatarfull": "https://cdn.example/avatar.jpg",
                            }
                        ]
                    }
                }
            )
        )

        profile = steam_auth.fetch_profile(self.steam_id)

        self.assertEqual(profile["persona_name"], "Gabe")
        self.assertEqual(profile["avatar_url"], "https://cdn.example/avatar.jpg")

    def test_user_gets_stable_username_and_profile(self):
        user = steam_auth.get_or_create_user(
            self.steam_id,
            {"persona_name": "Gabe", "avatar_url": "https://cdn.example/avatar.jpg"},
        )

        self.assertEqual(user.username, f"steam_{self.steam_id}")
        self.assertEqual(user.steam_profile.steam_id, self.steam_id)
        self.assertEqual(user.steam_profile.display_name, "Gabe")

    def test_second_login_reuses_user_and_updates_profile(self):
        user = steam_auth.get_or_create_user(self.steam_id, {"persona_name": "Old"})

        same_user = steam_auth.get_or_create_user(
            self.steam_id, {"persona_name": "New"}
        )

        self.assertEqual(same_user.pk, user.pk)
        self.assertEqual(SteamProfile.objects.count(), 1)
        self.assertEqual(
            SteamProfile.objects.get(steam_id=self.steam_id).persona_name, "New"
        )

    def test_existing_user_can_be_linked_through_profile(self):
        user = User.objects.create_user(username="old-timer")
        SteamProfile.objects.create(user=user, steam_id=self.steam_id)

        linked_user = steam_auth.get_or_create_user(
            self.steam_id, {"persona_name": "Gabe"}
        )

        self.assertEqual(linked_user.pk, user.pk)
        self.assertEqual(
            SteamProfile.objects.get(steam_id=self.steam_id).user_id, user.pk
        )


class SteamLoginViewTests(TestCase):
    """Маршруты входа: редирект в Steam и обработка callback."""

    steam_id = "76561197960287930"
    callback_url = "http://testserver/accounts/steam/callback/"

    def test_login_redirects_to_steam(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(steam_auth.OPENID_ENDPOINT))
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(response.url).query))
        self.assertEqual(query["openid.mode"], "checkid_setup")

        return_to = query["openid.return_to"]
        self.assertTrue(return_to.startswith(f"{self.callback_url}?"))
        return_query = dict(
            urllib.parse.parse_qsl(urllib.parse.urlsplit(return_to).query)
        )
        self.assertEqual(return_query["state"], self.client.session["steam_state"])

    def test_login_remembers_safe_next_page(self):
        self.client.get(reverse("login"), {"next": "/drives/"})

        self.assertEqual(self.client.session["steam_next"], "/drives/")
        self.assertTrue(self.client.session["steam_state"])

    def test_login_ignores_external_next_page(self):
        self.client.get(reverse("login"), {"next": "https://evil.example/"})

        self.assertIsNone(self.client.session.get("steam_next"))

    @patch(
        "games.views.steam_auth.fetch_profile",
        return_value={"persona_name": "Gabe", "avatar_url": ""},
    )
    @patch("games.views.steam_auth.verify_response", return_value=steam_id)
    def test_callback_creates_user_and_logs_in(self, verify_response, fetch_profile):
        session = self.client.session
        session["steam_next"] = "/drives/"
        session["steam_state"] = "test-state"
        session.save()

        response = self.client.get(
            reverse("steam_callback"),
            {"openid.mode": "id_res", "state": "test-state"},
        )

        self.assertRedirects(response, "/drives/", fetch_redirect_response=False)
        user = User.objects.get(username=f"steam_{self.steam_id}")
        self.assertEqual(user.steam_profile.persona_name, "Gabe")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    @patch(
        "games.views.steam_auth.fetch_profile",
        return_value={"persona_name": "Gabe", "avatar_url": ""},
    )
    @patch("games.views.steam_auth.verify_response", return_value=steam_id)
    def test_callback_shows_steam_name_in_header(self, verify_response, fetch_profile):
        session = self.client.session
        session["steam_state"] = "test-state"
        session.save()

        self.client.get(
            reverse("steam_callback"),
            {"openid.mode": "id_res", "state": "test-state"},
        )

        response = self.client.get(reverse("home"))

        self.assertContains(response, "Gabe")

    @patch(
        "games.views.steam_auth.verify_response",
        side_effect=steam_auth.SteamAuthError("bad signature"),
    )
    def test_callback_rejects_invalid_response(self, verify_response):
        session = self.client.session
        session["steam_state"] = "test-state"
        session.save()

        response = self.client.get(
            reverse("steam_callback"),
            {"openid.mode": "id_res", "state": "test-state"},
            follow=True,
        )

        self.assertContains(response, "Не удалось подтвердить вход через Steam")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_callback_without_state_is_rejected(self):
        response = self.client.get(
            reverse("steam_callback"), {"openid.mode": "id_res"}, follow=True
        )

        self.assertContains(response, "Не удалось подтвердить вход через Steam")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_callback_with_wrong_state_is_rejected(self):
        session = self.client.session
        session["steam_state"] = "expected-state"
        session.save()

        response = self.client.get(
            reverse("steam_callback"),
            {"openid.mode": "id_res", "state": "wrong-state"},
            follow=True,
        )

        self.assertContains(response, "Не удалось подтвердить вход через Steam")
        self.assertNotIn("_auth_user_id", self.client.session)

    @patch(
        "games.views.steam_auth.fetch_profile",
        return_value={"persona_name": "Gabe", "avatar_url": ""},
    )
    @patch("games.views.steam_auth.verify_response", return_value=steam_id)
    def test_callback_state_is_single_use(self, verify_response, fetch_profile):
        session = self.client.session
        session["steam_state"] = "one-time-state"
        session.save()

        first = self.client.get(
            reverse("steam_callback"),
            {"openid.mode": "id_res", "state": "one-time-state"},
        )
        self.assertEqual(first.status_code, 302)

        self.client.logout()
        second = self.client.get(
            reverse("steam_callback"),
            {"openid.mode": "id_res", "state": "one-time-state"},
            follow=True,
        )

        self.assertContains(second, "Не удалось подтвердить вход через Steam")
        self.assertNotIn("_auth_user_id", self.client.session)


class DriveViewsTests(ProfileFixtureMixin, TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u1", password="pass12345")
        self.client.force_login(self.user)

    def _post_drive(self, name: str, *, capacity: str = "2000", rpm: str = "7200",
                    recording: str = "cmr", primary: bool = False):
        return self.client.post(
            reverse("add_drive"),
            {
                "name": name,
                "capacity_gb": capacity,
                "rpm": rpm,
                "recording": recording,
                "is_primary": "on" if primary else "",
            },
        )

    def test_add_drive_with_specs(self):
        response = self._post_drive(
            "WD Blue WD20EZAZ", rpm="5400", recording="smr"
        )

        self.assertEqual(response.status_code, 302)
        drive = UserDrive.objects.get(user=self.user, name="WD Blue WD20EZAZ")
        self.assertEqual(drive.profile.slug, "hdd-smr")
        self.assertTrue(drive.smr)
        self.assertEqual(drive.specs, "2 ТБ · 5400 об/мин · SMR")

    def test_same_name_updates_specs_and_reports(self):
        self._post_drive("Seagate Barracuda", rpm="5400", recording="cmr")
        drive = UserDrive.objects.get(user=self.user, name="Seagate Barracuda")

        game = Game.objects.create(
            source=Game.Source.STEAM, external_id="5", title="G"
        )
        save_report(
            game=game, user=self.user, user_drive=drive,
            verdict=Report.Verdict.PLAYABLE,
        )

        self._post_drive("Seagate Barracuda", rpm="7200", recording="cmr")

        self.assertEqual(
            UserDrive.objects.filter(user=self.user, name="Seagate Barracuda").count(), 1
        )
        drive.refresh_from_db()
        self.assertEqual(drive.rpm, 7200)
        self.assertEqual(drive.profile.slug, "hdd-7200-cmr")

        report = Report.objects.get(game=game, user=self.user)
        self.assertEqual(report.drive_specs, "2 ТБ · 7200 об/мин · CMR")
        self.assertEqual(report.profile.slug, "hdd-7200-cmr")

    def test_empty_name_is_rejected(self):
        response = self._post_drive("")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(UserDrive.objects.filter(user=self.user).exists())

    def test_primary_drive_is_unique(self):
        self._post_drive("First", primary=True)
        self._post_drive("Second", primary=True)

        self.assertFalse(UserDrive.objects.get(user=self.user, name="First").is_primary)
        self.assertTrue(UserDrive.objects.get(user=self.user, name="Second").is_primary)

    def test_remove_drive_keeps_reports(self):
        self._post_drive("Seagate Barracuda")
        drive = UserDrive.objects.get(user=self.user, name="Seagate Barracuda")
        game = Game.objects.create(
            source=Game.Source.STEAM, external_id="5", title="G"
        )
        save_report(
            game=game, user=self.user, user_drive=drive,
            verdict=Report.Verdict.PLAYABLE,
        )

        response = self.client.post(reverse("remove_drive", args=[drive.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(UserDrive.objects.filter(pk=drive.pk).exists())
        report = Report.objects.get(game=game, user=self.user)
        self.assertEqual(report.drive_name, "Seagate Barracuda")
        self.assertEqual(report.profile.slug, "hdd-7200-cmr")

    def test_report_form_has_no_empty_drive_option(self):
        self._post_drive("Seagate Barracuda")

        form = ReportForm(user=self.user)

        self.assertTrue(form.fields["drive"].required)
        self.assertIsNone(form.fields["drive"].empty_label)

    def test_report_form_offers_name_and_specs(self):
        self._post_drive("WD Blue", rpm="5400", recording="cmr")

        form = ReportForm(user=self.user)
        labels = [str(label) for _, label in form.fields["drive"].choices]

        self.assertIn("WD Blue · 2 ТБ · 5400 об/мин · CMR", labels)

    def test_report_form_allows_no_drive_without_drives(self):
        form = ReportForm(user=self.user)

        self.assertFalse(form.fields["drive"].required)
        self.assertEqual(
            form.fields["drive"].empty_label, "Не знаю свой накопитель"
        )


class HealthTests(TestCase):
    def test_health_reports_ok_when_database_answers(self):
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_health_reports_error_when_database_is_down(self):
        with patch("config.health.connection") as connection:
            connection.cursor.side_effect = RuntimeError("database is down")

            response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "error"})

    def test_health_rejects_post(self):
        response = self.client.post(reverse("health"))

        self.assertEqual(response.status_code, 405)


class ErrorPageTests(TestCase):
    def test_unknown_page_uses_custom_404(self):
        response = self.client.get("/no-such-page/")

        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")
        self.assertContains(response, "Страница не найдена", status_code=404)

    def test_500_template_renders_without_context(self):
        from django.template.loader import render_to_string

        html = render_to_string("500.html")

        self.assertIn("Что-то сломалось", html)


class StaticFilesTests(TestCase):
    def test_favicon_redirects_to_svg(self):
        response = self.client.get("/favicon.ico")

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "/static/games/favicon.svg")

    def test_base_template_links_favicon(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, 'rel="icon"')
        self.assertContains(response, "/static/games/favicon.svg")
