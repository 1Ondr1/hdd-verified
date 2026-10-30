"""Админка: классы накопителей, каталог игр и модерация отчётов."""

from __future__ import annotations

from django.contrib import admin, messages
from django.db.models import Count
from django.urls import reverse
from django.utils.html import format_html

from games.models import (
    Ban,
    Complaint,
    DriveProfile,
    Game,
    Report,
    ReportLike,
    SteamProfile,
    UserDrive,
)


@admin.register(DriveProfile)
class DriveProfileAdmin(admin.ModelAdmin):
    list_display = ("label", "slug", "sort_order", "drive_count")
    list_editable = ("sort_order",)
    search_fields = ("label", "slug")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_drive_count=Count("owners"))

    @admin.display(description="Накопителей", ordering="_drive_count")
    def drive_count(self, obj: DriveProfile) -> int:
        return obj._drive_count


@admin.register(UserDrive)
class UserDriveAdmin(admin.ModelAdmin):
    list_display = ("user", "name", "capacity_gb", "rpm", "smr", "profile", "is_primary", "created")
    list_filter = ("is_primary", "profile", "rpm", "smr")
    search_fields = ("user__username", "name")
    autocomplete_fields = ("user",)


@admin.register(SteamProfile)
class SteamProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "steam_id", "user", "updated")
    search_fields = ("steam_id", "persona_name", "user__username")
    autocomplete_fields = ("user",)
    readonly_fields = ("created", "updated")


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = (
        "display_title", "title_en", "source", "external_id", "storage_gb",
        "requires_ssd", "report_count", "created",
    )
    list_filter = ("source", "requires_ssd", "genre")
    search_fields = ("title", "title_en", "title_ru", "title_uk", "=external_id")
    readonly_fields = ("created",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_report_count=Count("reports"))

    @admin.display(description="Название", ordering="title")
    def display_title(self, obj: Game) -> str:
        return obj.display_title

    @admin.display(description="Отчётов", ordering="_report_count")
    def report_count(self, obj: Game) -> int:
        return obj._report_count


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = (
        "game", "user", "drive_name", "profile", "verdict", "stutter",
        "load_speed", "install_size_gb", "hidden", "updated",
    )
    list_filter = (
        "verdict", "stutter", "load_speed", "hidden", "profile",
        "drive_rpm", "drive_smr",
    )
    search_fields = ("game__title", "user__username", "drive_name", "comment")
    autocomplete_fields = ("game", "user")
    readonly_fields = ("profile", "install_size_updated", "created", "updated")
    date_hierarchy = "updated"
    actions = ("hide", "unhide")
    list_select_related = ("game", "user", "profile")

    @admin.action(description="Скрыть выбранные отчёты")
    def hide(self, request, queryset):
        self._toggle(request, queryset, True)

    @admin.action(description="Вернуть выбранные отчёты")
    def unhide(self, request, queryset):
        self._toggle(request, queryset, False)

    def _toggle(self, request, queryset, hidden: bool) -> None:
        count = queryset.update(hidden=hidden)
        self.message_user(
            request,
            f"{'Скрыто' if hidden else 'Возвращено'} отчётов: {count}",
            messages.SUCCESS,
        )


@admin.register(ReportLike)
class ReportLikeAdmin(admin.ModelAdmin):
    list_display = ("report", "user", "created")
    search_fields = ("report__game__title", "user__username")
    autocomplete_fields = ("report", "user")
    readonly_fields = ("created",)
    list_select_related = ("report", "report__game", "user")


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ("report_link", "author", "reason", "resolved", "created")
    list_filter = ("resolved", "reason")
    search_fields = ("report__game__title", "report__comment", "author__username", "comment")
    autocomplete_fields = ("report", "author")
    readonly_fields = ("created",)
    date_hierarchy = "created"
    list_select_related = ("report", "report__game", "author")
    actions = ("resolve", "reopen")

    @admin.display(description="Отчёт", ordering="report")
    def report_link(self, obj: Complaint):
        url = reverse("admin:games_report_change", args=[obj.report_id])
        return format_html('<a href="{}">{}</a>', url, obj.report)

    @admin.action(description="Отметить жалобы обработанными")
    def resolve(self, request, queryset):
        self._toggle(request, queryset, True)

    @admin.action(description="Вернуть жалобы в работу")
    def reopen(self, request, queryset):
        self._toggle(request, queryset, False)

    def _toggle(self, request, queryset, resolved: bool) -> None:
        count = queryset.update(resolved=resolved)
        self.message_user(
            request,
            f"{'Обработано' if resolved else 'Возвращено в работу'} жалоб: {count}",
            messages.SUCCESS,
        )


@admin.register(Ban)
class BanAdmin(admin.ModelAdmin):
    list_display = ("steam_id", "full", "active", "reason_short", "created")
    list_filter = ("active", "full")
    search_fields = ("steam_id", "reason")
    readonly_fields = ("created", "updated")
    actions = ("activate", "deactivate")

    @admin.display(description="Причина")
    def reason_short(self, obj: Ban) -> str:
        return obj.reason[:60] + ("…" if len(obj.reason) > 60 else "")

    @admin.action(description="Включить выбранные баны")
    def activate(self, request, queryset):
        self._toggle(request, queryset, True)

    @admin.action(description="Снять выбранные баны")
    def deactivate(self, request, queryset):
        self._toggle(request, queryset, False)

    def _toggle(self, request, queryset, active: bool) -> None:
        count = queryset.update(active=active)
        self.message_user(
            request,
            f"{'Включено' if active else 'Снято'} банов: {count}",
            messages.SUCCESS,
        )
