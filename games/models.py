"""Модели каталога: игры, накопители и отчёты о совместимости.

Термины:

* **Профиль накопителя** — класс жёстких дисков, которые по-разному ведут
  себя в играх: 7200 CMR, 5400 CMR и SMR. Именно по профилям считается
  статистика: производитель и модель на поведение почти не влияют.
* **Накопитель пользователя** — полное название диска и три характеристики:
  объём, обороты и технология записи. Название нужно только для показа,
  оценки считаются по характеристикам.
* **Отчёт** — оценка игры; хранит снимок названия и характеристик, поэтому
  удаление диска из профиля не стирает историю.
"""

from __future__ import annotations

import re

from django.conf import settings
from django.db import models
from django.urls import reverse

from games.i18n import current_language, translate


class DriveProfile(models.Model):
    """Класс жёсткого диска — уровень, на котором сравниваются игры."""

    slug = models.SlugField("идентификатор", unique=True)
    label = models.CharField("название", max_length=100)
    sort_order = models.PositiveSmallIntegerField("порядок", default=100)

    class Meta:
        ordering = ("sort_order", "label")
        verbose_name = "профиль накопителя"
        verbose_name_plural = "профили накопителей"

    def __str__(self) -> str:
        return self.label


class UserDrive(models.Model):
    """Накопитель в профиле пользователя.

    Название хранится для показа, а сравниваются диски по характеристикам:
    обороты и технология записи определяют профиль. Поэтому «Seagate
    Barracuda 2 ТБ» и «WD Blue 2 ТБ» с одинаковыми характеристиками
    попадают в одну группу.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="пользователь", related_name="drives",
        on_delete=models.CASCADE,
    )
    name = models.CharField("название", max_length=200)
    capacity_gb = models.PositiveIntegerField("объём, ГБ", null=True, blank=True)
    rpm = models.PositiveSmallIntegerField("об/мин", null=True, blank=True)
    smr = models.BooleanField("SMR", null=True, blank=True, help_text="Пусто — неизвестно")
    profile = models.ForeignKey(
        DriveProfile,
        verbose_name="профиль",
        related_name="owners",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    is_primary = models.BooleanField("основной", default=False)
    created = models.DateTimeField("добавлен", auto_now_add=True)

    class Meta:
        ordering = ("-is_primary", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("user", "name"), name="uniq_user_drive_name"
            ),
        ]
        verbose_name = "накопитель пользователя"
        verbose_name_plural = "накопители пользователей"

    def __str__(self) -> str:
        return self.name

    @property
    def specs(self) -> str:
        """Характеристики для интерфейса: «2 ТБ · 7200 об/мин · CMR»."""
        return specs_text(self.capacity_gb, self.rpm, self.smr)


def format_capacity(gb: int) -> str:
    """Показать объём в удобных единицах: 2000 → «2 ТБ», 1500 → «1,5 ТБ»."""
    if gb >= 1000:
        terabytes = gb / 1000
        text = (
            str(int(terabytes))
            if terabytes == int(terabytes)
            else f"{terabytes:.1f}"
        )
        if current_language() != "en":
            text = text.replace(".", ",")
        return f"{text} {translate('common.tb')}"
    return f"{gb} {translate('common.gb')}"


def specs_text(capacity_gb: int | None, rpm: int | None, smr: bool | None) -> str:
    """Собрать строку характеристик на текущем языке."""
    parts: list[str] = []
    if capacity_gb:
        parts.append(format_capacity(capacity_gb))
    if rpm:
        parts.append(translate("common.rpm", n=rpm))
    if smr is True:
        parts.append("SMR")
    elif smr is False:
        parts.append("CMR")
    return " · ".join(parts)


class Game(models.Model):
    """Игра в каталоге — из Steam или Epic Games Store.

    Базовые поля (``title``, ``genre``, ``short_description``) хранят данные
    магазина на английском — это стандарт региона US. Русская и украинская
    версии лежат в отдельных полях и подтягиваются из магазина, если он их
    отдаёт. Интерфейс сам выбирает подходящий язык, поэтому база не
    привязана к русскому.
    """

    class Source(models.TextChoices):
        STEAM = "steam", "Steam"
        EPIC = "epic", "Epic Games"

    source = models.CharField(
        "магазин", max_length=10, choices=Source.choices, default=Source.STEAM
    )
    external_id = models.CharField("идентификатор в магазине", max_length=100)
    title = models.CharField("название", max_length=200)
    title_en = models.CharField("название на английском", max_length=200, blank=True)
    title_ru = models.CharField("название на русском", max_length=200, blank=True)
    title_uk = models.CharField("название на украинском", max_length=200, blank=True)
    genre = models.CharField("жанр", max_length=100, blank=True)
    genre_en = models.CharField("жанр на английском", max_length=100, blank=True)
    genre_ru = models.CharField("жанр на русском", max_length=100, blank=True)
    genre_uk = models.CharField("жанр на украинском", max_length=100, blank=True)
    release_year = models.PositiveSmallIntegerField("год выхода", null=True, blank=True)
    cover_url = models.URLField("обложка", max_length=500, blank=True)
    cover_url_ru = models.URLField(
        "обложка на русском",
        max_length=500,
        blank=True,
        help_text="Локализованный арт со страницы Steam",
    )
    cover_url_uk = models.URLField(
        "обложка на украинском",
        max_length=500,
        blank=True,
        help_text="Локализованный арт со страницы Steam",
    )
    short_description = models.TextField("краткое описание", blank=True)
    short_description_en = models.TextField("краткое описание на английском", blank=True)
    short_description_ru = models.TextField("краткое описание на русском", blank=True)
    short_description_uk = models.TextField("краткое описание на украинском", blank=True)
    store_url = models.URLField("страница магазина", max_length=500, blank=True)

    storage_gb = models.FloatField(
        "требуется места, ГБ", null=True, blank=True,
        help_text="Из требований магазина",
    )
    requires_ssd = models.BooleanField(
        "требует SSD", null=True, blank=True, help_text="Пусто — неизвестно"
    )

    created = models.DateTimeField("добавлена", auto_now_add=True)

    class Meta:
        ordering = ("title",)
        constraints = [
            models.UniqueConstraint(
                fields=("source", "external_id"), name="uniq_game_source_external"
            ),
        ]
        verbose_name = "игра"
        verbose_name_plural = "игры"

    def __str__(self) -> str:
        return self.display_title

    @property
    def display_title(self) -> str:
        """Название на языке интерфейса.

        Базовое ``title`` — английское, русское и украинское названия
        хранятся отдельно. Если локализации нет, показываем английский
        оригинал: пустая строка хуже, чем название на другом языке.
        """
        language = current_language()
        if language == "ru":
            return self.title_ru or self.title_en or self.title
        if language == "uk":
            return self.title_uk or self.title_en or self.title
        return self.title_en or self.title

    @property
    def display_genre(self) -> str:
        """Жанр на языке интерфейса."""
        language = current_language()
        if language == "ru":
            return self.genre_ru or self.genre_en or self.genre
        if language == "uk":
            return self.genre_uk or self.genre_en or self.genre
        return self.genre_en or self.genre

    @property
    def display_description(self) -> str:
        """Описание на языке интерфейса."""
        language = current_language()
        if language == "ru":
            return (
                self.short_description_ru
                or self.short_description_en
                or self.short_description
            )
        if language == "uk":
            return (
                self.short_description_uk
                or self.short_description_en
                or self.short_description
            )
        return self.short_description_en or self.short_description

    @property
    def cover_url_display(self) -> str:
        """Обложка на языке интерфейса.

        Это широкий арт 616×353, который Steam показывает на странице
        магазина. Адрес хранится в базе: он хешированный и меняется вместе
        с обложкой. Для русского и украинского есть отдельные версии
        с локализованным логотипом.
        """
        if self.source == self.Source.STEAM:
            language = current_language()
            if language == "ru" and self.cover_url_ru:
                return self.cover_url_ru
            if language == "uk" and self.cover_url_uk:
                return self.cover_url_uk
            if self.cover_url:
                return self.cover_url
            if self.external_id.isdigit():
                from games.services.steam import header_image

                return header_image(int(self.external_id), language)
        return self.cover_url

    @property
    def cover_fallback_url(self) -> str:
        """Запасная обложка, если основная не загрузилась.

        У Steam это базовая (английская) версия арта, затем обложка-заголовок
        460×215: у старых карточек широкой обложки может не быть вовсе.
        """
        primary = self.cover_url_display
        candidates: list[str] = []
        if self.source == self.Source.STEAM and self.external_id.isdigit():
            from games.services.steam import header_image

            appid = int(self.external_id)
            candidates = [
                header_image(appid, current_language()),
                self.cover_url,
                self.cover_url_ru,
                self.cover_url_uk,
                header_image(appid, "en"),
            ]
        for candidate in candidates:
            if candidate and candidate != primary:
                return candidate
        return ""

    @property
    def store_url_display(self) -> str:
        """Страница магазина на языке интерфейса."""
        language = current_language()
        if self.source == self.Source.STEAM and self.external_id.isdigit():
            steam_language = {
                "ru": "russian",
                "uk": "ukrainian",
            }.get(language, "english")
            return (
                f"https://store.steampowered.com/app/{self.external_id}/"
                f"?l={steam_language}"
            )
        if self.source == self.Source.EPIC and self.store_url:
            # У Epic нет украинской локали — для украинского показываем английскую.
            locale = "ru" if language == "ru" else "en-US"
            return re.sub(
                r"/(?:[a-z]{2}(?:-[A-Z]{2})?)/p/", f"/{locale}/p/", self.store_url
            )
        return self.store_url

    def get_absolute_url(self) -> str:
        return reverse("game_detail", args=[self.source, self.external_id])


class SteamProfile(models.Model):
    """Публичный профиль Steam, привязанный к пользователю сайта.

    Паролей на сайте нет: вход подтверждает Steam, а сайт получает только
    SteamID64 и публичные данные — ник и аватар. Ник и аватар обновляются
    при каждом входе, если настроен ``STEAM_API_KEY``; без ключа вход
    работает, но остаётся техническое имя ``steam_<id>``.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="пользователь",
        related_name="steam_profile",
        on_delete=models.CASCADE,
    )
    steam_id = models.CharField("SteamID64", max_length=20, unique=True)
    persona_name = models.CharField("ник в Steam", max_length=100, blank=True)
    avatar_url = models.URLField("аватар", max_length=500, blank=True)
    created = models.DateTimeField("создан", auto_now_add=True)
    updated = models.DateTimeField("обновлён", auto_now=True)

    class Meta:
        verbose_name = "профиль Steam"
        verbose_name_plural = "профили Steam"

    def __str__(self) -> str:
        return self.display_name

    @property
    def display_name(self) -> str:
        """Ник для интерфейса с откатом на техническое имя."""
        return self.persona_name or self.user.username


class Report(models.Model):
    """Оценка игры пользователем.

    Одна на пользователя и игру: если он сменил накопитель или удалил его,
    следующая оценка перезаписывает предыдущую, а не добавляет вторую.

    Название и характеристики накопителя — снимок на момент оценки: диск
    можно удалить из профиля, а отчёт останется понятным. Структурированные
    поля снимка нужны для фильтра отчётов по характеристикам.
    """

    class Verdict(models.TextChoices):
        PLAYABLE = "playable", "Играбельно"
        LIMITED = "limited", "С оговорками"
        UNPLAYABLE = "unplayable", "Неиграбельно"

    class Stutter(models.TextChoices):
        NONE = "none", "Нет"
        MINOR = "minor", "Небольшие"
        HEAVY = "heavy", "Сильные"

    class LoadSpeed(models.TextChoices):
        """Скорость загрузки до меню — диапазоны вместо секунд.

        Точные секунды пользователи почти никогда не замеряют, а «долго» от
        «очень долго» на HDD отличает минута, а не десятые.
        """

        FAST = "fast", "Быстро — до 15 с"
        NORMAL = "normal", "Нормально — 15–60 с"
        SLOW = "slow", "Долго — 1–3 мин"
        VERY_SLOW = "very_slow", "Очень долго — больше 3 мин"

    game = models.ForeignKey(
        Game, verbose_name="игра", related_name="reports", on_delete=models.CASCADE
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="автор", related_name="reports",
        on_delete=models.CASCADE,
    )
    drive_name = models.CharField("накопитель", max_length=200, blank=True)
    drive_specs = models.CharField("характеристики накопителя", max_length=200, blank=True)
    drive_capacity_gb = models.PositiveIntegerField(
        "объём накопителя, ГБ", null=True, blank=True
    )
    drive_rpm = models.PositiveSmallIntegerField(
        "обороты накопителя", null=True, blank=True
    )
    drive_smr = models.BooleanField(
        "SMR накопителя", null=True, blank=True, help_text="Пусто — неизвестно"
    )
    profile = models.ForeignKey(
        DriveProfile, verbose_name="профиль", related_name="reports",
        null=True, blank=True, on_delete=models.SET_NULL,
        help_text="Заполняется автоматически по характеристикам накопителя",
    )
    verdict = models.CharField("вердикт", max_length=20, choices=Verdict.choices)

    install_size_gb = models.FloatField(
        "размер игры, ГБ", null=True, blank=True,
        help_text="Сколько игра занимает на диске",
    )
    install_size_updated = models.DateTimeField(
        "размер обновлён", null=True, blank=True
    )

    stutter = models.CharField(
        "фризы", max_length=10, choices=Stutter.choices, blank=True
    )
    load_speed = models.CharField(
        "загрузка до меню", max_length=10, choices=LoadSpeed.choices, blank=True
    )
    comment = models.TextField("комментарий", blank=True)

    hidden = models.BooleanField("скрыт", default=False)
    created = models.DateTimeField("создан", auto_now_add=True)
    updated = models.DateTimeField("обновлён", auto_now=True)

    class Meta:
        ordering = ("-updated",)
        constraints = [
            models.UniqueConstraint(
                fields=("game", "user"), name="uniq_report_game_user"
            ),
        ]
        verbose_name = "отчёт"
        verbose_name_plural = "отчёты"

    def __str__(self) -> str:
        return f"{self.game} — {self.verdict_label}"

    def save(self, *args, **kwargs):
        """Сбросить машинные переводы, если комментарий изменился.

        Перевод привязан к конкретному тексту: после правки комментария
        старый перевод показывал бы уже не то, что написал автор. Поэтому
        при любом изменении текста удаляем готовые переводы — при следующем
        клике «Перевести» DeepL получит новый текст.
        """
        previous_comment = None
        if self.pk:
            previous_comment = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("comment", flat=True)
                .first()
            )
        super().save(*args, **kwargs)
        if previous_comment is not None and previous_comment != self.comment:
            self.translations.all().delete()

    @property
    def specs(self) -> str:
        """Снимок характеристик на текущем языке."""
        text = specs_text(self.drive_capacity_gb, self.drive_rpm, self.drive_smr)
        return text or self.drive_specs

    @property
    def verdict_label(self) -> str:
        return translate(f"verdict.{self.verdict}")

    @property
    def stutter_label(self) -> str:
        return translate(f"stutter.{self.stutter}") if self.stutter else ""

    @property
    def load_speed_label(self) -> str:
        return translate(f"load.{self.load_speed}") if self.load_speed else ""


class ReportLike(models.Model):
    """Отметка «Полезно» под отчётом.

    Одна на пользователя и отчёт: повторный клик снимает отметку. Свой
    отчёт отмечать нельзя — это проверяется во view, а не в модели,
    чтобы правило было видно рядом с остальными правами.
    """

    report = models.ForeignKey(
        Report, verbose_name="отчёт", related_name="likes", on_delete=models.CASCADE
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="пользователь",
        related_name="report_likes",
        on_delete=models.CASCADE,
    )
    created = models.DateTimeField("создан", auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("report", "user"), name="uniq_report_like_user"
            ),
        ]
        ordering = ("-created",)
        verbose_name = "отметка «полезно»"
        verbose_name_plural = "отметки «полезно»"

    def __str__(self) -> str:
        return f"{self.report_id} ← {self.user_id}"


class Complaint(models.Model):
    """Жалоба на отчёт.

    Жалобы не удаляют отчёт автоматически: они попадают в админку, где
    модератор решает, скрыть отчёт или отклонить жалобу. Почта не
    используется — список открывается в админке.
    """

    class Reason(models.TextChoices):
        SPAM = "spam", "Спам или реклама"
        ABUSE = "abuse", "Оскорбления"
        WRONG = "wrong", "Неверные данные"
        OTHER = "other", "Другое"

    report = models.ForeignKey(
        Report, verbose_name="отчёт", related_name="complaints", on_delete=models.CASCADE
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="автор жалобы",
        related_name="complaints",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    reason = models.CharField("причина", max_length=10, choices=Reason.choices)
    comment = models.TextField("комментарий", blank=True)
    resolved = models.BooleanField("обработана", default=False)
    created = models.DateTimeField("создана", auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("report", "author"), name="uniq_complaint_report_author"
            ),
        ]
        ordering = ("-created",)
        verbose_name = "жалоба"
        verbose_name_plural = "жалобы"

    def __str__(self) -> str:
        return f"Жалоба на отчёт {self.report_id}"


class Ban(models.Model):
    """Бан по SteamID64.

    Привязан к SteamID, а не к аккаунту сайта: удаление пользователя или
    пересоздание записи бан не снимает. Обычный бан запрещает писать,
    читать можно; полный закрывает сайт целиком.
    """

    steam_id = models.CharField("SteamID64", max_length=20, unique=True)
    reason = models.TextField("причина", blank=True)
    full = models.BooleanField(
        "полный бан",
        default=False,
        help_text="Закрывает и чтение: пользователь увидит только страницу блокировки.",
    )
    active = models.BooleanField("активен", default=True)
    created = models.DateTimeField("создан", auto_now_add=True)
    updated = models.DateTimeField("обновлён", auto_now=True)

    class Meta:
        ordering = ("-created",)
        verbose_name = "бан"
        verbose_name_plural = "баны"

    def __str__(self) -> str:
        return f"{self.steam_id}{' (полный)' if self.full else ''}"


class CommentTranslation(models.Model):
    """Машинный перевод комментария к отчёту на один язык.

    Храним результат, чтобы DeepL не вызывался повторно: один отзыв
    переводится максимум по разу на каждый язык.
    """

    report = models.ForeignKey(
        Report, verbose_name="отчёт", related_name="translations",
        on_delete=models.CASCADE,
    )
    language = models.CharField("язык перевода", max_length=10)
    text = models.TextField("перевод")
    created = models.DateTimeField("создан", auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("report", "language"), name="uniq_report_translation"
            ),
        ]
        verbose_name = "перевод комментария"
        verbose_name_plural = "переводы комментариев"

    def __str__(self) -> str:
        return f"{self.report_id} → {self.language}"
