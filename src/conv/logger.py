"""Логирование для conv — пишет в ~/.conv/conv.log с ротацией."""

from __future__ import annotations
import logging
import logging.handlers
import os
from pathlib import Path

LOG_DIR = Path.home() / ".conv"
LOG_FILE = LOG_DIR / "conv.log"
MAX_BYTES = 1 * 1024 * 1024  # 1 MB
BACKUP_COUNT = 5

_loggers: dict[str, logging.Logger] = {}
_initialized = False


def get_logger(name: str = "conv") -> logging.Logger:
    """Возвращает логгер для модуля. Создаёт файловый handler при первом вызове."""
    global _initialized

    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)

    if not _initialized:
        _initialized = True
        _setup_root()

    # Не добавляем повторные handler'ы
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)

        # Форматтер
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Консоль (stderr) — только WARNING+
        console = logging.StreamHandler()
        console.setLevel(logging.WARNING)
        console.setFormatter(fmt)
        logger.addHandler(console)

    _loggers[name] = logger
    return logger


def _setup_root():
    """Однократная инициализация корневого логгера с ротацией файла."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()

    # Убираем handler'ы по умолчанию
    root.handlers.clear()

    # Файловый handler с ротацией
    handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(fmt)

    root.setLevel(logging.DEBUG)
    root.addHandler(handler)

    root.info("=== conv logger started ===")
    root.info("Log file: %s", LOG_FILE)


def tail(n: int = 50) -> str:
    """Возвращает последние n строк лога."""
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            lines = f.readlines()
        return "".join(lines[-n:])
    except (FileNotFoundError, OSError) as e:
        return f"[Лог недоступен: {e}]"


def log_path() -> str:
    return str(LOG_FILE)
