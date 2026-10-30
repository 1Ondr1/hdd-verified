"""Небольшой слой переводов интерфейса.

Django-gettext здесь не используется: проект должен собираться без GNU
gettext и без компиляции ``.mo``. Строки лежат в одном словаре, а язык
берётся из активной локали Django (её переключает ``set_language``).
"""

from __future__ import annotations

from django.utils.translation import get_language

#: Ключ → (русский текст, английский текст).
TRANSLATIONS: dict[str, tuple[str, str]] = {
    # --- Общее ----------------------------------------------------------
    "app.tagline": (
        "Каталог совместимости игр с жёсткими дисками",
        "Game compatibility catalog for hard drives",
    ),
    "common.gb": ("ГБ", "GB"),
    "common.tb": ("ТБ", "TB"),
    "common.rpm": ("{n} об/мин", "{n} rpm"),
    "common.unknown": ("Не знаю", "Not sure"),
    "common.delete": ("Удалить", "Delete"),
    "common.reset": ("Сбросить", "Reset"),
    "common.show": ("Показать", "Show"),
    "common.close": ("Закрыть", "Close"),
    "common.cancel": ("Отмена", "Cancel"),
    # --- Шапка ----------------------------------------------------------
    "nav.drives": ("Мои диски", "My drives"),
    "nav.login": ("Вход", "Sign in"),
    "nav.logout": ("Выйти", "Sign out"),
    "nav.language": ("Язык", "Language"),
    # --- Главная и поиск ------------------------------------------------
    "home.title": (
        "Пойдёт ли игра на вашем жёстком диске?",
        "Will the game run on your hard drive?",
    ),
    "home.subtitle": (
        "Отчёты реальных людей и разбивка по классам накопителей.",
        "Reports from real players, broken down by drive class.",
    ),
    "home.placeholder": ("Например, Cyberpunk 2077", "For example, Cyberpunk 2077"),
    "home.search": ("Найти", "Search"),
    "home.recent": ("Недавно добавленные", "Recently added"),
    "search.title_tag": ("Поиск: {q} — HDD Verified", "Search: {q} — HDD Verified"),
    "search.heading": ("Результаты поиска", "Search results"),
    "search.empty": (
        "Ничего не найдено. Попробуйте другое название.",
        "Nothing found. Try another title.",
    ),
    "search.prompt": ("Введите название игры.", "Enter a game title."),
    # --- Мои диски ------------------------------------------------------
    "drives.title_tag": ("Мои диски — HDD Verified", "My drives — HDD Verified"),
    "drives.heading": ("Мои накопители", "My drives"),
    "drives.intro": (
        "Название нужно только для показа. Оценки считаются по характеристикам, "
        "поэтому диск другого производителя с такими же параметрами попадает "
        "в ту же группу.",
        "The name is only shown in the interface. Ratings are based on specs, "
        "so a drive from another manufacturer with the same parameters belongs "
        "to the same group.",
    ),
    "drives.primary": ("основной", "primary"),
    "drives.empty": (
        "Пока не добавлено ни одного накопителя.",
        "No drives added yet.",
    ),
    "drives.add_heading": ("Добавить накопитель", "Add a drive"),
    "drives.add_button": ("Добавить", "Add"),
    "drives.how_title": (
        "Как узнать характеристики диска",
        "How to find your drive specs",
    ),
    "drives.how_intro": (
        "Выполните команду в PowerShell. Она покажет модель, объём, тип диска "
        "и скорость вращения. Если диск не виден, запустите PowerShell от имени "
        "администратора.",
        "Run this command in PowerShell. It shows the model, capacity, media type "
        "and spindle speed. If the drive is missing, run PowerShell as administrator.",
    ),
    "drives.how_powershell": ("PowerShell (Windows)", "PowerShell (Windows)"),
    "drives.how_hint": ("Windows · Linux · macOS", "Windows · Linux · macOS"),
    "drives.how_powershell_note": (
        "MediaType = 3 — жёсткий диск, 4 — SSD. Если SpindleSpeed "
        "равен 0, накопитель не сообщает обороты — проверьте модель в интернете.",
        "MediaType = 3 means a hard drive and 4 means an SSD. If "
        "SpindleSpeed is 0, the drive does not report its speed — look the "
        "model up online.",
    ),
    "drives.how_cmd": ("Командная строка (Windows)", "Command Prompt (Windows)"),
    "drives.how_linux": ("Linux / macOS", "Linux / macOS"),
    "drives.how_cmd_note": (
        "Старый способ без PowerShell — модель, объём и интерфейс:",
        "The old way without PowerShell — model, capacity and interface:",
    ),
    "drives.how_linux_note": (
        "В Linux и macOS модель, объём и признак вращения показывает "
        "lsblk, а скорость — smartctl:",
        "On Linux and macOS, lsblk shows the model, capacity and rotation "
        "flag, while smartctl reports the speed:",
    ),
    "drives.how_recording": (
        "Технологию записи (CMR или SMR) универсальная команда не показывает: "
        "проверьте точную модель на сайте производителя. SMR-диски хуже "
        "справляются с потоковой подгрузкой игр.",
        "No universal command reports the recording technology (CMR or SMR): "
        "check the exact model on the manufacturer's website. SMR drives handle "
        "game asset streaming worse.",
    ),
    "drives.how_size_note": (
        "В форме ниже выберите объём и обороты из списка, а технологию записи "
        "укажите вручную.",
        "In the form below, pick the capacity and spindle speed from the list, "
        "and select the recording technology.",
    ),
    "drives.name_placeholder": (
        "Seagate Barracuda ST2000DM008",
        "Seagate Barracuda ST2000DM008",
    ),
    # --- Карточка игры --------------------------------------------------
    "game.overall": ("Общая оценка", "Overall rating"),
    "game.by_classes": ("По классам накопителей", "By drive class"),
    "game.rate_button": ("Оценить игру", "Rate this game"),
    "game.rate_edit": ("Изменить оценку", "Edit rating"),
    "game.rate_login": ("Войдите, чтобы оценить", "Sign in to rate"),
    "game.save_report": ("Сохранить отчёт", "Save report"),
    "game.delete_report": ("Удалить оценку", "Delete rating"),
    "game.delete_confirm": (
        "Удалить вашу оценку? Это действие нельзя отменить.",
        "Delete your rating? This cannot be undone.",
    ),
    "game.your_rating": ("Ваша оценка:", "Your rating:"),
    "game.no_drive": ("накопитель не указан", "drive not specified"),
    "game.add_drive_link": ("Добавьте свой диск", "Add your drive"),
    "game.add_drive_after": (", чтобы оценки были точнее.", " to make ratings more precise."),
    "game.reports": ("Отчёты", "Reports"),
    "game.no_reports": ("Пока никто не оставил отчёт.", "No reports yet."),
    "game.no_reports_filtered": (
        "С такими характеристиками отчётов нет.",
        "There are no reports with these specs.",
    ),
    "game.min_reports_one": (
        "Пока {n} отчёт — нужно минимум 2.",
        "Only {n} report so far — at least 2 are needed.",
    ),
    "game.min_reports_few": (
        "Пока {n} отчёта — нужно минимум 2.",
        "Only {n} reports so far — at least 2 are needed.",
    ),
    "game.min_reports_many": (
        "Пока {n} отчётов — нужно минимум 2.",
        "Only {n} reports so far — at least 2 are needed.",
    ),
    "game.no_reports_yet": (
        "Отчётов пока нет — станьте первым.",
        "No reports yet — be the first.",
    ),
    "game.review_mix": ("Выжимка из отчётов", "Report summary"),
    "game.prediction_title": ("На вашем диске", "On your drive"),
    "prediction.playable": ("Скорее играбельно", "Probably playable"),
    "prediction.mixed": ("Скорее с оговорками", "Probably with caveats"),
    "prediction.unplayable": ("Скорее неиграбельно", "Probably unplayable"),
    "prediction.no_reports": (
        "Отчётов для этого класса пока нет",
        "No reports for this drive class yet",
    ),
    "prediction.basis_one": (
        "По {n} отчёту на таком диске",
        "Based on {n} report for this drive class",
    ),
    "prediction.basis_few": (
        "По {n} отчётам на таком диске",
        "Based on {n} reports for this drive class",
    ),
    "prediction.basis_many": (
        "По {n} отчётам на таком диске",
        "Based on {n} reports for this drive class",
    ),
    "prediction.login_link": ("Войдите", "Sign in"),
    "prediction.login_after": (
        ", чтобы увидеть прогноз для своего диска.",
        " to see a prediction for your drive.",
    ),
    "prediction.add_drive_after": (
        ", чтобы увидеть прогноз для него.",
        " to see a prediction for it.",
    ),
    "prediction.add_specs": (
        "Укажите у диска обороты и технологию записи — без них прогноза нет.",
        "Set the spindle speed and recording type for your drive to get a prediction.",
    ),
    "game.reports_count_one": ("{n} отчёт", "{n} report"),
    "game.reports_count_few": ("{n} отчёта", "{n} reports"),
    "game.reports_count_many": ("{n} отчётов", "{n} reports"),
    "game.community_size": ("По отчётам: ~{n} ГБ", "From reports: ~{n} GB"),
    "game.size_no_reports": (
        "Пока нет отчётов с размером игры",
        "No reports with the game size yet",
    ),
    "game.size_updated": ("обновлено {date}", "updated {date}"),
    "game.size_stale": (
        "Данные о размере устарели — обновите отчёт.",
        "The size data is outdated — update a report.",
    ),
    "game.filter_my": ("Моя конфигурация", "My configuration"),
    "game.filter_active": ("Показаны отчёты: {n}", "Showing reports: {n}"),
    "game.install_size": ("Размер игры", "Game size"),
    "game.requirement": ("Требования", "Requirements"),
    "game.show_more": ("Читать полностью", "Read more"),
    "game.show_less": ("Свернуть", "Show less"),
    # --- Фильтр ---------------------------------------------------------
    "filter.rpm": ("Обороты", "RPM"),
    "filter.recording": ("Запись", "Recording"),
    "filter.any": ("Любые", "Any"),
    "filter.rpm_hint": (
        "Скорость вращения шпинделя: 5400 или 7200 об/мин. "
        "Чем выше, тем быстрее игра грузится.",
        "Spindle speed: 5400 or 7200 rpm. "
        "The higher it is, the faster the game loads.",
    ),
    "filter.recording_hint": (
        "CMR — обычная запись, SMR — черепичная. "
        "На SMR-дисках игры грузятся и обновляются заметно медленнее.",
        "CMR is conventional recording, SMR is shingled. "
        "Games load and update noticeably slower on SMR drives.",
    ),
    # --- Отчёты ---------------------------------------------------------
    "report.stutter": ("фризы: {value}", "stutter: {value}"),
    "report.load": ("загрузка: {value}", "loading: {value}"),
    "report.size": ("размер: ~{n} ГБ", "size: ~{n} GB"),
    "report.translate": ("Перевести", "Translate"),
    "report.translate_show": ("Показать перевод", "Show translation"),
    "report.translate_note": (
        "Машинный перевод — возможны неточности.",
        "Machine translation — may be inaccurate.",
    ),
    "report.translate_failed": (
        "Не удалось перевести комментарий: сервис перевода недоступен.",
        "Could not translate the comment: the translation service is unavailable.",
    ),
    "report.translate_unavailable": (
        "Перевод комментариев не настроен.",
        "Comment translation is not configured.",
    ),
    "report.translate_quota": (
        "Дневной лимит переводов исчерпан. Попробуйте завтра.",
        "Daily translation limit reached. Try again tomorrow.",
    ),
    "reports.more": ("Показать ещё", "Show more"),
    # --- Полезность и жалобы ---------------------------------------------
    "like.button": ("Полезно", "Helpful"),
    "like.add": ("Отметить как полезное", "Mark as helpful"),
    "like.remove": ("Убрать отметку", "Remove mark"),
    "like.own": ("Нельзя отмечать свой отчёт.", "You cannot mark your own review."),
    "complaint.link": ("Пожаловаться", "Report"),
    "complaint.reason": ("Причина", "Reason"),
    "complaint.reason.spam": ("Спам или реклама", "Spam or advertising"),
    "complaint.reason.abuse": ("Оскорбления", "Abuse"),
    "complaint.reason.wrong": ("Неверные данные", "Wrong data"),
    "complaint.reason.other": ("Другое", "Other"),
    "complaint.comment": ("Комментарий (необязательно)", "Comment (optional)"),
    "complaint.send": ("Отправить", "Send"),
    "complaint.own": ("Нельзя жаловаться на свой отчёт.", "You cannot report your own review."),
    "complaint.invalid": ("Проверьте причину жалобы.", "Check the complaint reason."),
    "verdict.playable": ("Играбельно", "Playable"),
    "verdict.limited": ("С оговорками", "With caveats"),
    "verdict.unplayable": ("Неиграбельно", "Unplayable"),
    "stutter.none": ("Нет", "None"),
    "stutter.minor": ("Небольшие", "Minor"),
    "stutter.heavy": ("Сильные", "Heavy"),
    "load.fast": ("Быстро — до 15 с", "Fast — under 15 s"),
    "load.normal": ("Нормально — 15–60 с", "Normal — 15–60 s"),
    "load.slow": ("Долго — 1–3 мин", "Slow — 1–3 min"),
    "load.very_slow": ("Очень долго — больше 3 мин", "Very slow — over 3 min"),
    # Короткие подписи для выпадающего списка в форме: слова ушли в подсказку.
    "load.short.fast": ("до 15 с", "under 15 s"),
    "load.short.normal": ("15–60 с", "15–60 s"),
    "load.short.slow": ("1–3 мин", "1–3 min"),
    "load.short.very_slow": ("больше 3 мин", "over 3 min"),
    "stutter.unspecified": ("Не указано", "Not specified"),
    "load.unspecified": ("Не указано", "Not specified"),
    # --- Уровни общей оценки -------------------------------------------
    "level.no_data": ("Мало данных", "Not enough data"),
    "level.playable": (
        "Играбельно в большинстве случаев",
        "Playable in most cases",
    ),
    "level.mixed": ("Зависит от накопителя", "Depends on the drive"),
    "level.unplayable": ("Скорее неиграбельно", "Probably unplayable"),
    "level.short_playable": ("Играбельно", "Playable"),
    "level.short_mixed": ("Зависит от диска", "Depends on the drive"),
    "level.short_unplayable": ("Неиграбельно", "Unplayable"),
    "note.storage": ("Нужно {n} ГБ", "Needs {n} GB"),
    "note.ssd": ("в требованиях указан SSD", "SSD is listed in the requirements"),
    # --- Формы ----------------------------------------------------------
    "form.name": ("Полное название", "Full name"),
    "form.capacity": ("Объём", "Capacity"),
    "form.rpm": ("Скорость вращения", "Spindle speed"),
    "form.recording": ("Технология записи", "Recording technology"),
    "form.primary": ("Основной диск", "Primary drive"),
    "form.name_help": (
        "Как написано на накопителе. Название видно в отчётах, "
        "а оценки считаются по характеристикам.",
        "As written on the drive. The name is shown in reports, "
        "while ratings are based on specs.",
    ),
    "form.cmr": ("CMR — обычная", "CMR — conventional"),
    "form.smr": ("SMR — черепичная", "SMR — shingled"),
    "form.verdict": ("Как играется?", "How does it run?"),
    "form.stutter": ("Фризы", "Stutter"),
    "form.load_speed": ("Загрузка до меню", "Load to menu"),
    "form.comment": ("Комментарий", "Comment"),
    "form.comment_placeholder": ("Что заметили?", "What did you notice?"),
    "form.load_help": (
        "Время от запуска до главного меню: до 15 с — быстро, "
        "15–60 с — нормально, 1–3 мин — долго, больше 3 мин — очень долго.",
        "Time from launch to the main menu: under 15 s — fast, "
        "15–60 s — normal, 1–3 min — slow, over 3 min — very slow.",
    ),
    "form.comment_help": (
        "Например: «фризы при переходе между локациями».",
        "For example: “stutter when moving between locations”.",
    ),
    "form.size": ("Сколько занимает игра, ГБ", "Installed size, GB"),
    "form.size_help": (
        "Проверьте размер папки игры. Размер обновляется вместе с отчётом.",
        "Check the game folder size. It is refreshed together with your report.",
    ),
    "form.size_placeholder": ("Например, 120", "For example, 120"),
    "form.drive": ("Накопитель", "Drive"),
    "form.drive_unknown": (
        "Не знаю свой накопитель",
        "I don't know my drive",
    ),
    "form.drive_hint": (
        "Оценка считается по характеристикам накопителя. "
        "Свои диски можно добавить в профиле.",
        "The rating is based on the drive specs. "
        "You can add your own drives in your profile.",
    ),
    # --- Сообщения ------------------------------------------------------
    "msg.report_saved": ("Спасибо! Отчёт сохранён.", "Thanks! Your report has been saved."),
    "msg.report_deleted": ("Оценка удалена.", "Your rating has been deleted."),
    "msg.drive_invalid": (
        "Проверьте название и характеристики.",
        "Check the name and specs.",
    ),
    "msg.drive_added": ("Накопитель «{name}» добавлен.", "Drive “{name}” added."),
    "msg.drive_updated": ("Накопитель «{name}» обновлён.", "Drive “{name}” updated."),
    "msg.drive_removed": (
        "Накопитель удалён из профиля.",
        "Drive removed from your profile.",
    ),
    "msg.welcome": ("Добро пожаловать!", "Welcome!"),
    "msg.complaint_sent": ("Жалоба отправлена. Спасибо!", "Complaint sent. Thank you!"),
    "msg.complaint_exists": (
        "Жалоба на этот отчёт уже отправлена.",
        "You have already reported this review.",
    ),
    # --- Аккаунт --------------------------------------------------------
    # Паролей на сайте нет: вход только через Steam OpenID.
    "auth.steam_error": (
        "Не удалось подтвердить вход через Steam. Попробуйте ещё раз.",
        "Could not verify your Steam sign-in. Please try again.",
    ),
    "auth.logged_out_title": (
        "Вы вышли из аккаунта",
        "You have signed out",
    ),
    "auth.login_again": ("Войти снова", "Sign in again"),
    "auth.home_link": ("на главную", "go home"),
    # --- Ошибки ---------------------------------------------------------
    "error.title": ("Не удалось загрузить игру", "Could not load the game"),
    "error.back": ("Вернуться на главную", "Back to the home page"),
    "error.not_found_title": ("Страница не найдена", "Page not found"),
    "error.not_found_text": (
        "Такой страницы нет или она переехала. Проверьте адрес или вернитесь на главную.",
        "This page does not exist or has moved. Check the address or go back home.",
    ),
    "error.server_title": ("Что-то сломалось", "Something went wrong"),
    "error.server_text": (
        "Ошибка на нашей стороне. Мы уже видим её в логах — попробуйте обновить страницу через минуту.",
        "The error is on our side. It is already in the logs — try refreshing in a minute.",
    ),
    # --- Блокировка -----------------------------------------------------
    "ban.title": ("Доступ ограничен", "Access restricted"),
    "ban.text": (
        "Администратор ограничил вашей учётной записи запись. Читать сайт можно.",
        "An administrator has restricted writing for your account. You can still read the site.",
    ),
    "ban.reason": ("Причина", "Reason"),
    "ban.logout": ("Выйти", "Sign out"),
}


#: Украинские строки: ключ → текст. Держим их отдельным словарём, чтобы не
#: переписывать все пары выше; если перевода нет, показываем русский текст.
UKRAINIAN: dict[str, str] = {
    # --- Общее ----------------------------------------------------------
    "app.tagline": "Каталог сумісності ігор із жорсткими дисками",
    "common.gb": "ГБ",
    "common.tb": "ТБ",
    "common.rpm": "{n} об/хв",
    "common.unknown": "Не знаю",
    "common.delete": "Видалити",
    "common.reset": "Скинути",
    "common.show": "Показати",
    "common.close": "Закрити",
    "common.cancel": "Скасувати",
    # --- Шапка ----------------------------------------------------------
    "nav.drives": "Мої диски",
    "nav.login": "Вхід",
    "nav.logout": "Вийти",
    "nav.language": "Мова",
    # --- Главная и поиск ------------------------------------------------
    "home.title": "Чи піде гра на вашому жорсткому диску?",
    "home.subtitle": "Звіти реальних людей і розподіл за класами накопичувачів.",
    "home.placeholder": "Наприклад, Cyberpunk 2077",
    "home.search": "Знайти",
    "home.recent": "Нещодавно додані",
    "search.title_tag": "Пошук: {q} — HDD Verified",
    "search.heading": "Результати пошуку",
    "search.empty": "Нічого не знайдено. Спробуйте іншу назву.",
    "search.prompt": "Введіть назву гри.",
    # --- Мои диски ------------------------------------------------------
    "drives.title_tag": "Мої диски — HDD Verified",
    "drives.heading": "Мої накопичувачі",
    "drives.intro": (
        "Назва потрібна лише для показу. Оцінки рахуються за характеристиками, "
        "тому диск іншого виробника з такими самими параметрами потрапляє "
        "до тієї самої групи."
    ),
    "drives.primary": "основний",
    "drives.empty": "Поки не додано жодного накопичувача.",
    "drives.add_heading": "Додати накопичувач",
    "drives.add_button": "Додати",
    "drives.how_title": "Як дізнатися характеристики диска",
    "drives.how_intro": (
        "Виконайте команду в PowerShell. Вона покаже модель, обсяг, тип диска "
        "й швидкість обертання. Якщо диск не видно, запустіть PowerShell від "
        "імені адміністратора."
    ),
    "drives.how_powershell": "PowerShell (Windows)",
    "drives.how_hint": "Windows · Linux · macOS",
    "drives.how_powershell_note": (
        "MediaType = 3 — жорсткий диск, 4 — SSD. Якщо SpindleSpeed "
        "дорівнює 0, накопичувач не повідомляє оберти — перевірте модель "
        "в інтернеті."
    ),
    "drives.how_cmd": "Командний рядок (Windows)",
    "drives.how_linux": "Linux / macOS",
    "drives.how_cmd_note": (
        "Старий спосіб без PowerShell — модель, обсяг та інтерфейс:"
    ),
    "drives.how_linux_note": (
        "У Linux і macOS модель, обсяг та ознаку обертання показує "
        "lsblk, а швидкість — smartctl:"
    ),
    "drives.how_recording": (
        "Технологію запису (CMR чи SMR) універсальна команда не показує: "
        "перевірте точну модель на сайті виробника. SMR-диски гірше "
        "справляються з потоковим підвантаженням ігор."
    ),
    "drives.how_size_note": (
        "У формі нижче виберіть обсяг та оберти зі списку, а технологію "
        "запису вкажіть вручну."
    ),
    "drives.name_placeholder": "Seagate Barracuda ST2000DM008",
    # --- Карточка игры --------------------------------------------------
    "game.overall": "Загальна оцінка",
    "game.by_classes": "За класами накопичувачів",
    "game.rate_button": "Оцінити гру",
    "game.rate_edit": "Змінити оцінку",
    "game.rate_login": "Увійдіть, щоб оцінити",
    "game.save_report": "Зберегти звіт",
    "game.delete_report": "Видалити оцінку",
    "game.delete_confirm": (
        "Видалити вашу оцінку? Цю дію не можна скасувати."
    ),
    "game.your_rating": "Ваша оцінка:",
    "game.no_drive": "накопичувач не вказано",
    "game.add_drive_link": "Додайте свій диск",
    "game.add_drive_after": ", щоб оцінки були точнішими.",
    "game.reports": "Звіти",
    "game.no_reports": "Поки ніхто не залишив звіт.",
    "game.no_reports_filtered": "З такими характеристиками звітів немає.",
    "game.min_reports_one": "Поки {n} звіт — потрібно щонайменше 2.",
    "game.min_reports_few": "Поки {n} звіти — потрібно щонайменше 2.",
    "game.min_reports_many": "Поки {n} звітів — потрібно щонайменше 2.",
    "game.no_reports_yet": "Звітів поки немає — станьте першим.",
    "game.review_mix": "Вижимка зі звітів",
    "game.prediction_title": "На вашому диску",
    "prediction.playable": "Скоріше за все, грабельно",
    "prediction.mixed": "Скоріше з застереженнями",
    "prediction.unplayable": "Скоріше неграбельно",
    "prediction.no_reports": "Звітів для цього класу поки немає",
    "prediction.basis_one": "За {n} звітом на такому диску",
    "prediction.basis_few": "За {n} звітами на такому диску",
    "prediction.basis_many": "За {n} звітами на такому диску",
    "prediction.login_link": "Увійдіть",
    "prediction.login_after": ", щоб побачити прогноз для свого диска.",
    "prediction.add_drive_after": ", щоб побачити прогноз для нього.",
    "prediction.add_specs": (
        "Вкажіть у диска оберти й технологію запису — без них прогнозу немає."
    ),
    "game.reports_count_one": "{n} звіт",
    "game.reports_count_few": "{n} звіти",
    "game.reports_count_many": "{n} звітів",
    "game.community_size": "За звітами: ~{n} ГБ",
    "game.size_no_reports": "Поки немає звітів із розміром гри",
    "game.size_updated": "оновлено {date}",
    "game.size_stale": "Дані про розмір застаріли — оновіть звіт.",
    "game.filter_my": "Моя конфігурація",
    "game.filter_active": "Показано звіти: {n}",
    "game.install_size": "Розмір гри",
    "game.requirement": "Вимоги",
    "game.show_more": "Читати повністю",
    "game.show_less": "Згорнути",
    # --- Фильтр ---------------------------------------------------------
    "filter.rpm": "Оберти",
    "filter.recording": "Запис",
    "filter.any": "Будь-які",
    "filter.rpm_hint": (
        "Швидкість обертання шпинделя: 5400 або 7200 об/хв. "
        "Чим вище, тим швидше гра завантажується."
    ),
    "filter.recording_hint": (
        "CMR — звичайний запис, SMR — черепичний. "
        "На SMR-дисках ігри завантажуються й оновлюються помітно повільніше."
    ),
    # --- Отчёты ---------------------------------------------------------
    "report.stutter": "фризи: {value}",
    "report.load": "завантаження: {value}",
    "report.size": "розмір: ~{n} ГБ",
    "report.translate": "Перекласти",
    "report.translate_show": "Показати переклад",
    "report.translate_note": "Машинний переклад — можливі неточності.",
    "report.translate_failed": (
        "Не вдалося перекласти коментар: сервіс перекладу недоступний."
    ),
    "report.translate_unavailable": "Переклад коментарів не налаштовано.",
    "report.translate_quota": "Денний ліміт перекладів вичерпано. Спробуйте завтра.",
    "reports.more": "Показати ще",
    # --- Корисність і скарги --------------------------------------------
    "like.button": "Корисно",
    "like.add": "Позначити як корисне",
    "like.remove": "Зняти позначку",
    "like.own": "Не можна позначати власний відгук.",
    "complaint.link": "Поскаржитися",
    "complaint.reason": "Причина",
    "complaint.reason.spam": "Спам або реклама",
    "complaint.reason.abuse": "Образи",
    "complaint.reason.wrong": "Неправильні дані",
    "complaint.reason.other": "Інше",
    "complaint.comment": "Коментар (необов'язково)",
    "complaint.send": "Надіслати",
    "complaint.own": "Не можна скаржитися на власний відгук.",
    "complaint.invalid": "Перевірте причину скарги.",
    "verdict.playable": "Грабельно",
    "verdict.limited": "Із застереженнями",
    "verdict.unplayable": "Неграбельно",
    "stutter.none": "Немає",
    "stutter.minor": "Невеликі",
    "stutter.heavy": "Сильні",
    "load.fast": "Швидко — до 15 с",
    "load.normal": "Нормально — 15–60 с",
    "load.slow": "Довго — 1–3 хв",
    "load.very_slow": "Дуже довго — понад 3 хв",
    "load.short.fast": "до 15 с",
    "load.short.normal": "15–60 с",
    "load.short.slow": "1–3 хв",
    "load.short.very_slow": "понад 3 хв",
    "stutter.unspecified": "Не вказано",
    "load.unspecified": "Не вказано",
    # --- Уровни общей оценки -------------------------------------------
    "level.no_data": "Мало даних",
    "level.playable": "Грабельно в більшості випадків",
    "level.mixed": "Залежить від накопичувача",
    "level.unplayable": "Скоріше неграбельно",
    "level.short_playable": "Грабельно",
    "level.short_mixed": "Залежить від диска",
    "level.short_unplayable": "Неграбельно",
    "note.storage": "Потрібно {n} ГБ",
    "note.ssd": "у вимогах вказано SSD",
    # --- Формы ----------------------------------------------------------
    "form.name": "Повна назва",
    "form.capacity": "Обсяг",
    "form.rpm": "Швидкість обертання",
    "form.recording": "Технологія запису",
    "form.primary": "Основний диск",
    "form.name_help": (
        "Як написано на накопичувачі. Назва видна у звітах, "
        "а оцінки рахуються за характеристиками."
    ),
    "form.cmr": "CMR — звичайна",
    "form.smr": "SMR — черепична",
    "form.verdict": "Як грається?",
    "form.stutter": "Фризи",
    "form.load_speed": "Завантаження до меню",
    "form.comment": "Коментар",
    "form.comment_placeholder": "Що помітили?",
    "form.load_help": (
        "Час від запуску до головного меню: до 15 с — швидко, "
        "15–60 с — нормально, 1–3 хв — довго, понад 3 хв — дуже довго."
    ),
    "form.comment_help": "Наприклад: «фризи під час переходу між локаціями».",
    "form.size": "Скільки займає гра, ГБ",
    "form.size_help": (
        "Перевірте розмір папки гри. Розмір оновлюється разом зі звітом."
    ),
    "form.size_placeholder": "Наприклад, 120",
    "form.drive": "Накопичувач",
    "form.drive_unknown": "Не знаю свій накопичувач",
    "form.drive_hint": (
        "Оцінка рахується за характеристиками накопичувача. "
        "Свої диски можна додати в профілі."
    ),
    # --- Сообщения ------------------------------------------------------
    "msg.report_saved": "Дякуємо! Звіт збережено.",
    "msg.report_deleted": "Оцінку видалено.",
    "msg.drive_invalid": "Перевірте назву й характеристики.",
    "msg.drive_added": "Накопичувач «{name}» додано.",
    "msg.drive_updated": "Накопичувач «{name}» оновлено.",
    "msg.drive_removed": "Накопичувач видалено з профілю.",
    "msg.welcome": "Ласкаво просимо!",
    "msg.complaint_sent": "Скаргу надіслано. Дякуємо!",
    "msg.complaint_exists": "Скаргу на цей відгук уже надіслано.",
    # --- Аккаунт --------------------------------------------------------
    "auth.steam_error": (
        "Не вдалося підтвердити вхід через Steam. Спробуйте ще раз."
    ),
    "auth.logged_out_title": "Ви вийшли з акаунта",
    "auth.login_again": "Увійти знову",
    "auth.home_link": "на головну",
    # --- Ошибки ---------------------------------------------------------
    "error.title": "Не вдалося завантажити гру",
    "error.back": "Повернутися на головну",
    "error.not_found_title": "Сторінку не знайдено",
    "error.not_found_text": (
        "Такої сторінки немає або вона переїхала. Перевірте адресу або поверніться на головну."
    ),
    "error.server_title": "Щось зламалося",
    "error.server_text": (
        "Помилка на нашому боці. Ми вже бачимо її в логах — спробуйте оновити сторінку за хвилину."
    ),
    # --- Блокування -----------------------------------------------------
    "ban.title": "Доступ обмежено",
    "ban.text": (
        "Адміністратор обмежив запис для вашого акаунта. Читати сайт можна."
    ),
    "ban.reason": "Причина",
    "ban.logout": "Вийти",
}


def current_language() -> str:
    """Короткий код активного языка: ``ru``, ``en`` или ``uk``."""
    language = (get_language() or "ru").lower()
    if language.startswith("en"):
        return "en"
    if language.startswith("uk"):
        return "uk"
    return "ru"


def translate(key: str, **params) -> str:
    """Перевести строку по ключу и подставить параметры."""
    russian, english = TRANSLATIONS.get(key, (key, key))
    language = current_language()
    if language == "en":
        text = english
    elif language == "uk":
        text = UKRAINIAN.get(key, russian)
    else:
        text = russian
    if params:
        try:
            return text.format(**params)
        except (KeyError, IndexError):
            return text
    return text


def plural_form(n: int) -> str:
    """Форма множественного числа для числа ``n``: one, few или many.

    Для английского хватает one/many, для русского и украинского нужны все три.
    """
    if current_language() == "en":
        return "one" if n == 1 else "many"
    if n % 10 == 1 and n % 100 != 11:
        return "one"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "few"
    return "many"


def translate_plural(key: str, n: int, **params) -> str:
    """Строка с числом и правильной формой: ``{n} отчёт / {n} отчёта``."""
    return translate(f"{key}_{plural_form(n)}", n=n, **params)


class LazyText:
    """Переводимый текст, который вычисляется при отрисовке.

    Нужен для подписей форм: они создаются при импорте, а язык известен
    только во время запроса.
    """

    __slots__ = ("key", "params")

    def __init__(self, key: str, **params):
        self.key = key
        self.params = params

    def __str__(self) -> str:
        return translate(self.key, **self.params)

    def __repr__(self) -> str:
        return str(self)
