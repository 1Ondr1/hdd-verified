"""Настройки Django для проекта HDD Verified.

Секреты и переключатели читаются из переменных окружения.
Локальные значения удобно держать в файле ``.env`` в корне проекта
(см. ``.env.example``).
"""

from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from config.env import load_env

load_env()

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    """Прочитать булево значение из окружения."""
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: tuple[str, ...] = ()) -> list[str]:
    """Прочитать список, разделённый запятыми."""
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()] or list(default)


def env_int(name: str, default: int) -> int:
    """Прочитать целое число из окружения."""
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


# --- Безопасность -----------------------------------------------------------

DEBUG = env_bool("DJANGO_DEBUG", True)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY обязателен при DJANGO_DEBUG=0")
    SECRET_KEY = "django-insecure-dev-only-do-not-use-in-production"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ("localhost", "127.0.0.1", "[::1]"))

# На хостинге HTTPS обычно завершается на прокси, и до Django запрос доходит
# по http. Без этого заголовка request.scheme останется http, а Steam вернёт
# пользователя на http-адрес callback.
if env_bool("DJANGO_TRUST_PROXY_SSL_HEADER", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


# --- Приложения -------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "games",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

# Django 6 всегда подключает кэширующий загрузчик шаблонов, поэтому
# в разработке задаём загрузчики явно — иначе правки шаблонов не видны
# без перезапуска сервера.
_TEMPLATE_LOADERS = [
    "django.template.loaders.filesystem.Loader",
    "django.template.loaders.app_directories.Loader",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": not DEBUG,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
            **({"loaders": _TEMPLATE_LOADERS} if DEBUG else {}),
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# --- База данных ------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# --- Аутентификация ---------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "home"


# --- Локализация ------------------------------------------------------------

LANGUAGE_CODE = "ru-ru"
LANGUAGES = [
    ("ru", "Русский"),
    ("en", "English"),
    ("uk", "Українська"),
]
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True


# --- Статика ----------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"


# --- Почта ------------------------------------------------------------------

MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.console.EmailBackend",
    },
}


# --- Кэш --------------------------------------------------------------------

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "hdd-verified",
    }
}


# --- Внешние API ------------------------------------------------------------

# Регион и язык данных — по стандарту США: так Steam и Epic отдают
# одинаковый набор полей и цену, а локализованные названия запрашиваются
# отдельно для каждого языка интерфейса.
STEAM_COUNTRY = os.environ.get("STEAM_COUNTRY", "us")
STEAM_LANGUAGE = os.environ.get("STEAM_LANGUAGE", "english")
STEAM_CACHE_TTL = env_int("STEAM_CACHE_TTL", 60 * 60 * 24)

# Epic Games Store: публичный GraphQL не требует ключа. Регион и локаль —
# американские, русские названия подтягиваются отдельным запросом.
EPIC_COUNTRY = os.environ.get("EPIC_COUNTRY", "US")
EPIC_LOCALE = os.environ.get("EPIC_LOCALE", "en")
EPIC_CACHE_TTL = env_int("EPIC_CACHE_TTL", 60 * 60 * 24)

# Вход через Steam OpenID не требует ключа: сайт получает только SteamID64.
# Ключ Web API нужен лишь для ника и аватара — без него вход работает.
STEAM_API_KEY = os.environ.get("STEAM_API_KEY", "")

# DeepL переводит комментарии к отчётам по кнопке. Ключ берём из окружения:
# без него кнопка просто не показывается. Бесплатные ключи заканчиваются
# на «:fx» и работают через отдельный адрес API.
DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY", "")
DEEPL_TIMEOUT = env_int("DEEPL_TIMEOUT", 15)
