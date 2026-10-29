"""Загрузка переменных окружения из файла ``.env``.

Проект намеренно обходится без внешних зависимостей: формат ``.env``
примитивен, а лишний пакет в проде — лишняя поверхность обновлений.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_env(path: Path = DEFAULT_ENV_FILE) -> None:
    """Прочитать ``KEY=VALUE`` из ``path`` и положить в ``os.environ``.

    Уже заданные переменные окружения имеют приоритет: файл лишь
    дополняет их, но никогда не перезаписывает.
    """
    if not path.is_file():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
