"""Агрегация отчётов: общая оценка игры и разбивка по профилям.

Общая оценка нужна тем, кто не знает свой накопитель. Она сознательно
осторожна: сглаживается, требует минимум данных и всегда сопровождается
разбивкой по профилям, чтобы «68%» не выглядело приговором.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from django.db.models import Avg, Case, Count, FloatField, QuerySet, Sum, Value, When
from django.utils import timezone

from games.i18n import translate
from games.models import Game, Report

#: Вклад вердикта в оценку (0..1).
VERDICT_SCORE = {
    Report.Verdict.PLAYABLE: 1.0,
    Report.Verdict.LIMITED: 0.5,
    Report.Verdict.UNPLAYABLE: 0.0,
}

#: Отчёт без указания накопителя менее информативен, но не бесполезен.
DRIVE_REPORT_WEIGHT = 1.0
NO_DRIVE_REPORT_WEIGHT = 0.4

#: Байесовское сглаживание: один голос не должен давать 100%.
PRIOR_WEIGHT = 2.0
PRIOR_SCORE = 0.5

#: Ниже этого эффективного числа отчётов оценка не показывается.
MIN_EFFECTIVE_REPORTS = 2.0

LEVEL_PLAYABLE = "playable"
LEVEL_MIXED = "mixed"
LEVEL_UNPLAYABLE = "unplayable"
LEVEL_NO_DATA = "no_data"

#: Сколько дней размер игры считается актуальным: три месяца. Патчи и
#: обновления быстро делают старые замеры бесполезными, поэтому такие отчёты
#: продолжают влиять на оценку, но не на размер. Если свежих замеров нет,
#: показываем последний известный размер с датой его обновления.
SIZE_FRESH_DAYS = 90


def _score_expression():
    """SQL-выражение: вердикт отчёта как число от 0 до 1."""
    return Case(
        *(When(verdict=verdict, then=Value(score)) for verdict, score in VERDICT_SCORE.items()),
        default=Value(0.0),
        output_field=FloatField(),
    )


def _level_by_score(score: float) -> str:
    """Уровень по самой оценке, без порога «мало отчётов».

    Нужен там, где важен цвет конкретной строки, а не осторожная общая
    оценка: разбивка по классам накопителей и прогноз для диска.
    """
    if score >= 0.7:
        return LEVEL_PLAYABLE
    if score >= 0.4:
        return LEVEL_MIXED
    return LEVEL_UNPLAYABLE


def _level_for(score: float, effective_reports: float) -> str:
    if effective_reports < MIN_EFFECTIVE_REPORTS:
        return LEVEL_NO_DATA
    return _level_by_score(score)


LEVEL_KEYS = {
    LEVEL_NO_DATA: "level.no_data",
    LEVEL_PLAYABLE: "level.playable",
    LEVEL_MIXED: "level.mixed",
    LEVEL_UNPLAYABLE: "level.unplayable",
}

#: Короткие подписи для узкой колонки в разбивке по классам.
SHORT_LEVEL_KEYS = {
    LEVEL_PLAYABLE: "level.short_playable",
    LEVEL_MIXED: "level.short_mixed",
    LEVEL_UNPLAYABLE: "level.short_unplayable",
}


@dataclass(frozen=True)
class OverallRating:
    """Общая оценка игры по всем отчётам."""

    level: str
    label: str
    score: float
    percent: int
    reports: int
    effective_reports: float

    @property
    def has_data(self) -> bool:
        return self.level != LEVEL_NO_DATA


@dataclass(frozen=True)
class ProfileRating:
    """Оценка игры на одном классе накопителей."""

    slug: str
    label: str
    reports: int
    score: float
    percent: int
    level: str

    @property
    def level_label(self) -> str:
        """Короткая подпись уровня: цвет полоски продублирован словом."""
        return translate(SHORT_LEVEL_KEYS[self.level])


@dataclass(frozen=True)
class VerdictShare:
    """Доля отчётов с конкретным вердиктом — выжимка из отзывов."""

    key: str
    label: str
    count: int
    percent: int


@dataclass(frozen=True)
class DrivePrediction:
    """Осторожный прогноз для накопителя пользователя.

    Считается по отчётам того же класса диска. Минимум отчётов не
    требуется: подпись «предположительно» честно говорит, что данных мало.
    """

    drive_name: str
    drive_specs: str
    level: str
    label: str
    reports: int


@dataclass(frozen=True)
class SizeSummary:
    """Размер игры по свежим пользовательским замерам."""

    community_gb: float | None
    reports: int
    stale_reports: int
    latest: datetime | None

    @property
    def has_any(self) -> bool:
        return bool(self.community_gb or self.stale_reports)


def visible_reports(game: Game) -> QuerySet[Report]:
    return game.reports.filter(hidden=False)


def overall_rating(game: Game) -> OverallRating:
    """Посчитать общую оценку игры."""
    weight = Case(
        When(drive_name="", then=Value(NO_DRIVE_REPORT_WEIGHT)),
        default=Value(DRIVE_REPORT_WEIGHT),
        output_field=FloatField(),
    )
    totals = visible_reports(game).aggregate(
        reports=Count("id"),
        weighted_score=Sum(_score_expression() * weight),
        weight=Sum(weight),
    )

    reports = totals["reports"] or 0
    total_weight = totals["weight"] or 0.0
    level = _level_for(PRIOR_SCORE, total_weight)

    if not total_weight:
        return OverallRating(
            level=level,
            label=translate(LEVEL_KEYS[level]),
            score=PRIOR_SCORE,
            percent=round(PRIOR_SCORE * 100),
            reports=0,
            effective_reports=0.0,
        )

    score = (totals["weighted_score"] + PRIOR_WEIGHT * PRIOR_SCORE) / (
        total_weight + PRIOR_WEIGHT
    )
    level = _level_for(score, total_weight)
    return OverallRating(
        level=level,
        label=translate(LEVEL_KEYS[level]),
        score=score,
        percent=round(score * 100),
        reports=reports,
        effective_reports=total_weight,
    )


def profile_ratings(game: Game) -> list[ProfileRating]:
    """Разбивка по профилям накопителей, от быстрых к медленным."""
    rows = (
        visible_reports(game)
        .filter(profile__isnull=False)
        .values("profile__slug", "profile__label", "profile__sort_order")
        .annotate(reports=Count("id"), score=Avg(_score_expression()))
        .order_by("profile__sort_order")
    )
    ratings: list[ProfileRating] = []
    for row in rows:
        score = row["score"] or 0.0
        ratings.append(
            ProfileRating(
                slug=row["profile__slug"],
                label=row["profile__label"],
                reports=row["reports"],
                score=score,
                percent=round(score * 100),
                level=_level_by_score(score),
            )
        )
    return ratings


def verdict_breakdown(game: Game) -> list[VerdictShare]:
    """Сколько отчётов каждого вердикта — короткая выжимка для карточки."""
    counts = {
        row["verdict"]: row["reports"]
        for row in visible_reports(game)
        .values("verdict")
        .annotate(reports=Count("id"))
    }
    total = sum(counts.values())
    return [
        VerdictShare(
            key=verdict,
            label=translate(f"verdict.{verdict}"),
            count=counts.get(verdict, 0),
            percent=round(counts.get(verdict, 0) * 100 / total) if total else 0,
        )
        for verdict in Report.Verdict.values
    ]


def drive_prediction(game: Game, drive) -> DrivePrediction | None:
    """Предположительная оценка игры на диске пользователя.

    Класс диска берём по его профилю: обороты и технология записи. Если
    у диска не указаны характеристики, прогноза нет — подсказку покажет
    шаблон.
    """
    profile = getattr(drive, "profile", None)
    if profile is None:
        return None

    row = next(
        (rating for rating in profile_ratings(game) if rating.slug == profile.slug),
        None,
    )
    reports = row.reports if row else 0
    if row is None or not reports:
        level = LEVEL_NO_DATA
        label = translate("prediction.no_reports")
    else:
        level = _level_by_score(row.score)
        label = translate(f"prediction.{level}")

    return DrivePrediction(
        drive_name=drive.name,
        drive_specs=drive.specs,
        level=level,
        label=label,
        reports=reports,
    )


def filtered_reports(
    game: Game,
    *,
    rpm: str | int | None = None,
    recording: str | None = None,
    limit: int | None = None,
) -> QuerySet[Report]:
    """Отчёты, отфильтрованные по оборотам и технологии записи.

    Пустое или некорректное значение означает «любые». Объём диска на
    поведение игры не влияет, поэтому в фильтре его нет. Отчёты без
    снимка характеристик (например, старые или без диска) в фильтр не
    попадают.
    """
    reports = (
        visible_reports(game)
        .select_related("user__steam_profile", "profile")
        .annotate(like_count=Count("likes"))
    )
    rpm_value = _as_int(rpm)
    if rpm_value is not None:
        reports = reports.filter(drive_rpm=rpm_value)
    if recording == "smr":
        reports = reports.filter(drive_smr=True)
    elif recording == "cmr":
        reports = reports.filter(drive_smr=False)
    # Сначала отчёты, которые сообщество отметило полезными, затем свежие.
    reports = reports.order_by("-like_count", "-updated")
    return reports[:limit] if limit else reports


def _as_int(value: str | int | None) -> int | None:
    """Привести значение фильтра к числу, иначе — «любое»."""
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def size_summary(game: Game) -> SizeSummary:
    """Свежий пользовательский размер игры.

    В расчёт идут замеры за последние три месяца: медиана устойчива к
    единичному «у меня 300 ГБ». Если свежих замеров нет, остаётся последний
    известный размер — с датой, когда его обновили.
    """
    cutoff = timezone.now() - timedelta(days=SIZE_FRESH_DAYS)
    sized = visible_reports(game).filter(install_size_gb__isnull=False)
    fresh = list(
        sized.filter(install_size_updated__gte=cutoff)
        .exclude(install_size_gb__lt=1)
        .exclude(install_size_gb__gt=2000)
        .values("install_size_gb", "install_size_updated")
    )
    stale = sized.exclude(install_size_updated__gte=cutoff).count()

    if fresh:
        values = [row["install_size_gb"] for row in fresh]
        return SizeSummary(
            community_gb=round(statistics.median(values), 1),
            reports=len(values),
            stale_reports=stale,
            latest=max(row["install_size_updated"] for row in fresh),
        )

    # Свежих замеров нет — держим последний известный размер и его дату.
    last = (
        sized.filter(install_size_updated__isnull=False)
        .exclude(install_size_gb__lt=1)
        .exclude(install_size_gb__gt=2000)
        .order_by("-install_size_updated")
        .values("install_size_gb", "install_size_updated")
        .first()
    )
    return SizeSummary(
        community_gb=round(last["install_size_gb"], 1) if last else None,
        reports=0,
        stale_reports=stale,
        latest=last["install_size_updated"] if last else None,
    )


def requirement_note(game: Game) -> str:
    """Короткая заметка о требованиях магазина к накопителю."""
    parts: list[str] = []
    if game.storage_gb:
        parts.append(
            translate("note.storage", n=f"{game.storage_gb:g}")
        )
    if game.requires_ssd is True:
        parts.append(translate("note.ssd"))
    return " · ".join(parts)


def recent_reports(game: Game, limit: int = 20) -> Iterable[Report]:
    """Свежие отчёты для блока комментариев."""
    return filtered_reports(game, limit=limit)

