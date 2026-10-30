"""Формы: накопители, фильтр отчётов и сами отчёты."""

from __future__ import annotations

from django import forms

from games.i18n import LazyText, translate
from games.models import Complaint, Report, UserDrive, format_capacity
from games.services.drives import profile_for

#: Основные объёмы жёстких дисков. Пустое значение — «не знаю»: объём
#: полезен для понимания записи, но на класс накопителя не влияет.
CAPACITY_VALUES = (
    250, 320, 500, 750,
    1000, 1500, 2000, 3000, 4000, 6000, 8000,
    10000, 12000, 14000, 16000, 18000, 20000, 22000, 24000,
)

RPM_VALUES = (5400, 7200, 10000, 15000)


def capacity_choices(empty_label: str) -> list[tuple[str, str]]:
    """Объёмы для выпадающего списка."""
    return [("", empty_label), *[(str(value), format_capacity(value)) for value in CAPACITY_VALUES]]


def rpm_choices(empty_label: str) -> list[tuple[str, str]]:
    """Обороты для выпадающего списка."""
    return [
        ("", empty_label),
        *[(str(value), translate("common.rpm", n=value)) for value in RPM_VALUES],
    ]


def recording_choices(empty_label: str) -> list[tuple[str, str]]:
    """Технология записи для выпадающего списка."""
    return [
        ("", empty_label),
        ("cmr", translate("form.cmr")),
        ("smr", translate("form.smr")),
    ]


class NoColonFormMixin:
    """Подписи без двоеточий — так формы выглядят опрятнее."""

    def __init__(self, *args, **kwargs):
        # Django задаёт label_suffix в __init__, поэтому класс-атрибут
        # здесь не работает — передаём явно.
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)


class AddDriveForm(NoColonFormMixin, forms.ModelForm):
    """Добавить накопитель: полное название и три характеристики."""

    capacity_gb = forms.ChoiceField(label=LazyText("form.capacity"), required=False)
    rpm = forms.ChoiceField(label=LazyText("form.rpm"), required=False)
    recording = forms.ChoiceField(label=LazyText("form.recording"), required=False)

    field_order = ("name", "capacity_gb", "rpm", "recording", "is_primary")

    class Meta:
        model = UserDrive
        fields = ("name", "is_primary")
        labels = {
            "name": LazyText("form.name"),
            "is_primary": LazyText("form.primary"),
        }
        widgets = {
            "name": forms.TextInput(),
        }
        help_texts = {
            "name": LazyText("form.name_help"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        unknown = translate("common.unknown")
        self.fields["capacity_gb"].choices = capacity_choices(unknown)
        self.fields["rpm"].choices = rpm_choices(unknown)
        self.fields["recording"].choices = recording_choices(unknown)
        self.fields["name"].widget.attrs["placeholder"] = translate(
            "drives.name_placeholder"
        )

    def save(self, commit: bool = True) -> UserDrive:
        drive = super().save(commit=False)
        drive.capacity_gb = _as_int(self.cleaned_data.get("capacity_gb"))
        drive.rpm = _as_int(self.cleaned_data.get("rpm"))
        drive.smr = {
            "cmr": False,
            "smr": True,
        }.get(self.cleaned_data.get("recording") or "")
        drive.profile = profile_for(rpm=drive.rpm, smr=drive.smr)
        if commit:
            drive.save()
        return drive


class UserDriveChoiceField(forms.ModelChoiceField):
    """Показать в списке название и характеристики, а не только название."""

    def label_from_instance(self, drive: UserDrive) -> str:
        return f"{drive.name} · {drive.specs}" if drive.specs else drive.name


class ReportFilterForm(NoColonFormMixin, forms.Form):
    """Фильтр отчётов по характеристикам накопителя."""

    rpm = forms.ChoiceField(label=LazyText("filter.rpm"), required=False)
    recording = forms.ChoiceField(label=LazyText("filter.recording"), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        any_label = translate("filter.any")
        self.fields["rpm"].choices = rpm_choices(any_label)
        self.fields["recording"].choices = recording_choices(any_label)
        self.fields["rpm"].help_text = translate("filter.rpm_hint")
        self.fields["recording"].help_text = translate("filter.recording_hint")


class ReportForm(NoColonFormMixin, forms.ModelForm):
    """Оценка игры на своём накопителе."""

    drive = UserDriveChoiceField(
        queryset=UserDrive.objects.none(),
        label=LazyText("form.drive"),
        required=False,
    )
    install_size_gb = forms.FloatField(
        label=LazyText("form.size"),
        required=False,
        min_value=1,
        max_value=2000,
        widget=forms.NumberInput(attrs={"step": "0.1", "min": "1", "max": "2000"}),
        help_text=LazyText("form.size_help"),
    )

    class Meta:
        model = Report
        fields = ("verdict", "stutter", "load_speed", "comment")
        labels = {
            "verdict": LazyText("form.verdict"),
            "stutter": LazyText("form.stutter"),
            "load_speed": LazyText("form.load_speed"),
            "comment": LazyText("form.comment"),
        }
        widgets = {
            "verdict": forms.RadioSelect,
            "comment": forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {
            "load_speed": LazyText("form.load_help"),
            "comment": LazyText("form.comment_help"),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        drives = UserDrive.objects.filter(user=user).select_related("profile")

        self.fields["drive"].queryset = drives
        self.fields["drive"].help_text = translate("form.drive_hint")
        self.fields["install_size_gb"].widget.attrs["placeholder"] = translate(
            "form.size_placeholder"
        )
        self.fields["comment"].widget.attrs["placeholder"] = translate(
            "form.comment_placeholder"
        )
        if drives.exists():
            self.fields["drive"].required = True
            # Пустой пункт «выберите вариант» здесь только мешает: если
            # диск есть, оценка всегда привязана к одному из них.
            self.fields["drive"].empty_label = None
            if not self.initial.get("drive"):
                self.fields["drive"].initial = (
                    drives.filter(is_primary=True).values_list("pk", flat=True).first()
                    or drives.first().pk
                )
        else:
            # Накопителя в профиле нет — разрешаем оценить без него:
            # такой отчёт идёт только в общую оценку.
            self.fields["drive"].required = False
            self.fields["drive"].empty_label = translate("form.drive_unknown")

        # Убираем пустой пункт «Выберите вариант» из обязательного вердикта.
        self.fields["verdict"].choices = [
            (value, translate(f"verdict.{value}")) for value, _ in Report.Verdict.choices
        ]
        self.fields["stutter"].choices = [
            ("", translate("stutter.unspecified")),
            *[(value, translate(f"stutter.{value}")) for value, _ in Report.Stutter.choices],
        ]
        # В списке только периоды: слова «быстро/долго» ушли в подсказку к полю.
        self.fields["load_speed"].choices = [
            ("", translate("load.unspecified")),
            *[(value, translate(f"load.short.{value}")) for value, _ in Report.LoadSpeed.choices],
        ]


class ComplaintForm(NoColonFormMixin, forms.ModelForm):
    """Жалоба на отчёт: причина и необязательное пояснение."""

    reason = forms.ChoiceField(
        label=LazyText("complaint.reason"),
        choices=[
            (value, LazyText(f"complaint.reason.{value}"))
            for value in Complaint.Reason.values
        ],
    )
    comment = forms.CharField(
        label=LazyText("complaint.comment"),
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    class Meta:
        model = Complaint
        fields = ("reason", "comment")


def _as_int(value: str | None) -> int | None:
    """Превратить значение из выпадающего списка в число или ``None``."""
    return int(value) if value else None
