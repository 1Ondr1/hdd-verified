"""HTTP-слой: каталог, поиск, накопители и отчёты."""

from __future__ import annotations

import secrets
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from games.forms import AddDriveForm, ComplaintForm, ReportFilterForm, ReportForm
from games.i18n import current_language, translate
from games.models import (
    CommentTranslation,
    Complaint,
    Game,
    Report,
    ReportLike,
    UserDrive,
)
from games.services import epic, stats, steam
from games.services import search as game_search
from games.services import steam_auth
from games.services import translate as translation_service
from games.services.epic import is_valid_external_id
from games.services.games import get_or_create_game
from games.services.permissions import block_banned
from games.services.reports import save_report

#: Сколько отчётов показывать сразу. Остальные — по кнопке «Показать ещё».
REPORTS_PER_PAGE = 10


def _validate_game_id(source: str, external_id: str) -> None:
    """Не пускать в магазины и сеть заведомо некорректные адреса."""
    if source == Game.Source.STEAM and external_id.isdigit():
        return
    if source == Game.Source.EPIC and is_valid_external_id(external_id):
        return
    raise Http404("Игра не найдена")


def home(request):
    """Главная: поиск и недавно добавленные игры."""
    return render(
        request,
        "games/home.html",
        {"games": Game.objects.order_by("-created")[:12], "q": request.GET.get("q", "")},
    )


@require_GET
def search(request):
    """Поиск игр в Steam и Epic Games."""
    query = request.GET.get("q", "").strip()
    results: list = []
    error = ""
    if len(query) >= 2:
        try:
            results = game_search.search_games(query, limit=20)
        except game_search.SearchError as exc:
            error = str(exc)
    return render(
        request,
        "games/search.html",
        {"q": query, "results": results, "error": error},
    )


@require_GET
def game_search_api(request):
    """Автодополнение поиска игр."""
    query = request.GET.get("q", "").strip()
    results = []
    if len(query) >= 2:
        try:
            results = [
                {
                    "url": item.url,
                    "name": item.name,
                    "image": item.image,
                    "fallback": item.fallback_image,
                    "source": item.source,
                }
                for item in game_search.search_games(query, limit=8)
            ]
        except game_search.SearchError:
            results = []
    return JsonResponse({"results": results})


def game_detail(request, source: str, external_id: str):
    """Карточка игры: общая оценка, разбивка по накопителям и отчёт."""
    _validate_game_id(source, external_id)
    try:
        game = get_or_create_game(source, external_id)
    except (steam.SteamError, epic.EpicError) as exc:
        return render(request, "games/error.html", {"message": str(exc)}, status=502)

    # Игра из Epic могла уже быть в каталоге из Steam — ведём на её адрес.
    if game.get_absolute_url() != request.path:
        return redirect(game)

    return render(request, "games/game_detail.html", _game_context(request, game))


@require_GET
def legacy_game_detail(request, appid: int):
    """Старые ссылки ``/game/<AppID>/`` — на новый адрес с магазином."""
    try:
        game = get_or_create_game(Game.Source.STEAM, str(appid))
    except steam.SteamError as exc:
        return render(request, "games/error.html", {"message": str(exc)}, status=502)
    return redirect(game, permanent=True)


@require_POST
def legacy_submit_report(request, appid: int):
    """Старая форма отчёта: перенаправляем на актуальную карточку."""
    return redirect("game_detail", Game.Source.STEAM, str(appid))


@login_required
@require_POST
@block_banned
def submit_report(request, source: str, external_id: str):
    """Сохранить или обновить отчёт пользователя."""
    _validate_game_id(source, external_id)
    game = get_object_or_404(Game, source=source, external_id=external_id)
    form = ReportForm(request.POST, user=request.user)
    if not form.is_valid():
        return render(
            request,
            "games/game_detail.html",
            _game_context(request, game, form),
        )

    data = form.cleaned_data
    save_report(
        game=game,
        user=request.user,
        user_drive=data["drive"],
        verdict=data["verdict"],
        stutter=data["stutter"],
        load_speed=data["load_speed"],
        install_size_gb=data["install_size_gb"],
        comment=data["comment"],
    )
    messages.success(request, translate("msg.report_saved"))
    return redirect(game)


@login_required
@require_POST
@block_banned
def delete_report(request, pk: int):
    """Удалить свою оценку игры. Чужие отчёты недоступны."""
    report = get_object_or_404(Report, pk=pk, user=request.user)
    game = report.game
    report.delete()
    messages.success(request, translate("msg.report_deleted"))
    return redirect(game)


@login_required
@require_POST
@block_banned
def toggle_like(request, pk: int):
    """Поставить или снять отметку «Полезно».

    Свой отчёт отмечать нельзя: это накрутка, а не оценка полезности.
    Повторный клик снимает отметку — отдельной кнопки «убрать» нет.
    """
    report = get_object_or_404(Report, pk=pk, hidden=False)
    if report.user_id == request.user.pk:
        messages.error(request, translate("like.own"))
        return redirect(_back_url(request, report))

    like, created = ReportLike.objects.get_or_create(
        report=report, user=request.user
    )
    if not created:
        like.delete()
    return redirect(_back_url(request, report))


@login_required
@require_POST
@block_banned
def complain(request, pk: int):
    """Отправить жалобу на отчёт. Одна жалоба на отчёт от пользователя."""
    report = get_object_or_404(Report, pk=pk, hidden=False)
    if report.user_id == request.user.pk:
        messages.error(request, translate("complaint.own"))
        return redirect(_back_url(request, report))

    form = ComplaintForm(request.POST)
    if not form.is_valid():
        messages.error(request, translate("complaint.invalid"))
        return redirect(_back_url(request, report))

    _, created = Complaint.objects.get_or_create(
        report=report,
        author=request.user,
        defaults={
            "reason": form.cleaned_data["reason"],
            "comment": form.cleaned_data["comment"],
        },
    )
    messages.success(
        request,
        translate("msg.complaint_sent" if created else "msg.complaint_exists"),
    )
    return redirect(_back_url(request, report))


@login_required
@require_POST
@block_banned
def translate_comment(request, pk: int):
    """Перевести комментарий отчёта на язык интерфейса и вернуться назад."""
    report = get_object_or_404(Report, pk=pk, hidden=False)
    language = current_language()

    translation = report.translations.filter(language=language).first()
    if translation is None and report.comment.strip():
        if not translation_service.available():
            messages.error(request, translate("report.translate_unavailable"))
            return redirect(_back_url(request, report))
        if translation_service.quota_exhausted(request.user.pk):
            messages.error(request, translate("report.translate_quota"))
            return redirect(_back_url(request, report))
        try:
            text = translation_service.translate(report.comment, language)
        except translation_service.TranslationError:
            messages.error(request, translate("report.translate_failed"))
            return redirect(_back_url(request, report))
        translation_service.consume_quota(request.user.pk)
        translation, _ = CommentTranslation.objects.get_or_create(
            report=report, language=language, defaults={"text": text}
        )

    return redirect(_back_url(request, report, translated=bool(translation)))


def _back_url(request, report: Report, *, translated: bool = False) -> str:
    """Вернуть пользователя на ту же страницу с фильтрами и якорем отчёта."""
    back = request.POST.get("next") or ""
    if not url_has_allowed_host_and_scheme(
        back, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        back = reverse("game_detail", args=[report.game.source, report.game.external_id])

    parts = urlsplit(back)
    query = dict(parse_qsl(parts.query))
    if translated:
        query["translated"] = str(report.pk)
    else:
        query.pop("translated", None)
    url = urlunsplit(("", "", parts.path, urlencode(query), ""))
    return f"{url}#report-{report.pk}"


@login_required
def my_drives(request):
    """Список своих накопителей и формы добавления."""
    return render(request, "games/drives.html", _drives_context(request))


@login_required
@require_POST
@block_banned
def add_drive(request):
    """Добавить накопитель в профиль: название и характеристики."""
    form = AddDriveForm(request.POST)
    if not form.is_valid():
        messages.error(request, translate("msg.drive_invalid"))
        return render(request, "games/drives.html", _drives_context(request, form=form))

    drive = form.save(commit=False)
    user_drive, created = UserDrive.objects.update_or_create(
        user=request.user,
        name=drive.name,
        defaults={
            "capacity_gb": drive.capacity_gb,
            "rpm": drive.rpm,
            "smr": drive.smr,
            "profile": drive.profile,
            "is_primary": drive.is_primary,
        },
    )
    if user_drive.is_primary:
        request.user.drives.exclude(pk=user_drive.pk).update(is_primary=False)

    # Отчёты хранят снимок характеристик: если пользователь исправил
    # данные диска, оценки должны переехать в правильный класс.
    request.user.reports.filter(drive_name=user_drive.name).update(
        drive_specs=user_drive.specs,
        drive_capacity_gb=user_drive.capacity_gb,
        drive_rpm=user_drive.rpm,
        drive_smr=user_drive.smr,
        profile=user_drive.profile,
    )

    messages.success(
        request,
        translate(
            "msg.drive_added" if created else "msg.drive_updated",
            name=user_drive.name,
        ),
    )
    return redirect("my_drives")


@login_required
@require_POST
@block_banned
def remove_drive(request, pk: int):
    """Убрать накопитель из своего профиля (отчёты сохраняются)."""
    request.user.drives.filter(pk=pk).delete()
    messages.success(request, translate("msg.drive_removed"))
    return redirect("my_drives")


@require_GET
def steam_login(request):
    """Начать вход через Steam: сразу увести на страницу подтверждения.

    Адрес возврата запоминаем в сессии, чтобы после ответа Steam вернуть
    пользователя туда, куда он шёл (например, на карточку игры).
    """
    next_url = request.GET.get("next", "")
    safe_next = ""
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        request.session["steam_next"] = next_url
        safe_next = next_url
    else:
        request.session.pop("steam_next", None)

    if request.user.is_authenticated:
        request.session.pop("steam_state", None)
        return redirect(safe_next or "home")

    # Одноразовый state привязывает ответ Steam к этой сессии: чужой или
    # повторно использованный callback не сможет залогинить пользователя.
    state = secrets.token_urlsafe(32)
    request.session["steam_state"] = state

    callback = request.build_absolute_uri(reverse("steam_callback"))
    return_to = f"{callback}?{urlencode({'state': state})}"
    realm = f"{request.scheme}://{request.get_host()}"
    return redirect(steam_auth.build_login_url(return_to, realm))


@require_GET
def steam_callback(request):
    """Проверить ответ Steam, войти и вернуть пользователя на прежнюю страницу."""
    next_url = request.session.pop("steam_next", "")

    state = request.GET.get("state", "")
    expected_state = request.session.pop("steam_state", "")
    if (
        not state
        or not expected_state
        or not secrets.compare_digest(state, expected_state)
    ):
        messages.error(request, translate("auth.steam_error"))
        return redirect("home")

    callback = request.build_absolute_uri(reverse("steam_callback"))
    expected_return_to = f"{callback}?{urlencode({'state': state})}"

    try:
        steam_id = steam_auth.verify_response(request.GET, expected_return_to)
        profile = steam_auth.fetch_profile(steam_id)
        user = steam_auth.get_or_create_user(steam_id, profile)
    except steam_auth.SteamAuthError:
        messages.error(request, translate("auth.steam_error"))
        return redirect("home")

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    messages.success(request, translate("msg.welcome"))

    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect("home")


def _game_context(request, game: Game, form: ReportForm | None = None) -> dict:
    user = request.user
    my_report: Report | None = None
    drive = None
    if user.is_authenticated:
        my_report = Report.objects.filter(game=game, user=user).first()
        drive = user.drives.filter(is_primary=True).first() or user.drives.first()
        if form is None:
            form = ReportForm(user=user, initial=_report_initial(my_report, user))

    filter_form = ReportFilterForm(request.GET or None)
    filters = filter_form.cleaned_data if filter_form.is_valid() else {}
    paginator = Paginator(
        stats.filtered_reports(
            game,
            rpm=filters.get("rpm"),
            recording=filters.get("recording"),
        ),
        REPORTS_PER_PAGE,
    )
    page_obj = paginator.get_page(request.GET.get("page"))
    reports = list(page_obj.object_list)

    # Готовые переводы и отметки «Полезно» подтягиваем одним запросом
    # на страницу, чтобы шаблон не ходил в базу для каждого отчёта.
    language = current_language()
    translations = {
        row.report_id: row.text
        for row in CommentTranslation.objects.filter(
            report__in=reports, language=language
        )
    }
    liked_ids = set()
    if user.is_authenticated:
        liked_ids = set(
            ReportLike.objects.filter(user=user, report__in=reports).values_list(
                "report_id", flat=True
            )
        )
    for report in reports:
        report.comment_translation = translations.get(report.pk)
        report.liked_by_me = report.pk in liked_ids

    try:
        translated_id = int(request.GET.get("translated", ""))
    except (TypeError, ValueError):
        translated_id = None

    return {
        "game": game,
        "overall": stats.overall_rating(game),
        "profiles": stats.profile_ratings(game),
        "verdict_mix": stats.verdict_breakdown(game),
        "prediction": stats.drive_prediction(game, drive) if drive else None,
        "requirement_note": stats.requirement_note(game),
        "size": stats.size_summary(game),
        "reports": reports,
        "reports_total": paginator.count,
        "page_obj": page_obj,
        "translated_id": translated_id,
        "translate_available": translation_service.available(),
        "filter_form": filter_form,
        "filter_active": any(filters.values()),
        "my_filter_query": _my_filter_query(user) if user.is_authenticated else "",
        "form": form,
        "report_form_open": bool(form and form.is_bound and form.errors),
        "my_report": my_report,
        "has_drives": user.is_authenticated and user.drives.exists(),
    }


def _report_initial(report: Report | None, user) -> dict:
    """Подставить в форму уже оставленный отчёт, чтобы его было удобно править."""
    if report is None:
        return {}
    return {
        "drive": _drive_id_for_report(report, user),
        "verdict": report.verdict,
        "stutter": report.stutter,
        "load_speed": report.load_speed,
        "install_size_gb": report.install_size_gb,
        "comment": report.comment,
    }


def _drive_id_for_report(report: Report, user) -> int | None:
    """Найти в профиле диск, на который ссылается отчёт, по названию.

    Связи по внешнему ключу нет: отчёт хранит снимок, а диск мог быть
    удалён. Если диск на месте — подставляем его в форму.
    """
    if not report.drive_name:
        return None
    return (
        user.drives.filter(name=report.drive_name)
        .values_list("pk", flat=True)
        .first()
    )


def _my_filter_query(user) -> str:
    """Ссылка «моя конфигурация»: фильтр по характеристикам основного диска."""
    drive = user.drives.filter(is_primary=True).first() or user.drives.first()
    if drive is None:
        return ""
    params: dict[str, str] = {}
    if drive.rpm:
        params["rpm"] = str(drive.rpm)
    if drive.smr is True:
        params["recording"] = "smr"
    elif drive.smr is False:
        params["recording"] = "cmr"
    return urlencode(params)


def _drives_context(request, *, form: AddDriveForm | None = None) -> dict:
    return {
        "drives": request.user.drives.select_related("profile"),
        "form": form or AddDriveForm(),
    }
