"""История конвертаций + конфиг.
   Linux:   ~/.config/conv/
   Windows: %APPDATA%\conv\        (роуминг профиля)
   macOS:   ~/Library/Application Support/conv/
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path

HISTORY_FILE_NAME = "history.json"
CONFIG_FILE_NAME = "config.json"


def _config_dir() -> Path:
    """Кроссплатформенная директория конфига (с поддержкой роуминга на Windows)."""
    if platform.system() == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif platform.system() == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "conv"


HISTORY_FILE = _config_dir() / HISTORY_FILE_NAME
MAX_ENTRIES = 100


@dataclass
class HistoryEntry:
    """Одна запись в истории конвертации/переименования."""
    timestamp: float = 0.0
    operation: str = ""
    input_name: str = ""
    output_name: str = ""
    src_fmt: str = ""
    dst_fmt: str = ""
    ok: bool = False
    src_size: int = 0
    dst_size: int = 0
    took: float = 0.0
    error: str = ""


class HistoryManager:
    """Управляет историей конвертаций."""

    def __init__(self, max_entries: int = MAX_ENTRIES):
        self._max = max_entries
        self._mutex = __import__("threading").Lock()
        self._ensure_dir()
        self._migrate_old()

    @staticmethod
    def _ensure_dir():
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _migrate_old():
        """Перенос истории из ~/.conv/history.json в новое расположение."""
        old = Path.home() / ".conv" / "history.json"
        if old.exists() and not HISTORY_FILE.exists():
            try:
                shutil.copy2(str(old), str(HISTORY_FILE))
            except OSError:
                pass
            try:
                old.unlink()
            except OSError:
                pass

    def add(self, entry: HistoryEntry) -> None:
        """Добавить запись и сохранить."""
        with self._mutex:
            entries = self._load()
            entries.insert(0, asdict(entry))
            if len(entries) > self._max:
                entries = entries[:self._max]
            self._save(entries)

    def add_from_result(self, result, operation: str) -> None:
        """Добавить запись из ConvertResult."""
        req = result.request
        out_name = result.output_path.name if result.output_path else ""
        dst_fmt = f".{result.output_path.suffix.lstrip('.')}" if result.output_path else ""
        entry = HistoryEntry(
            timestamp=time.time(),
            operation=operation,
            input_name=req.input_path.name,
            output_name=out_name,
            src_fmt=req.input_ext,
            dst_fmt=dst_fmt,
            ok=result.ok,
            src_size=result.src_size,
            dst_size=result.dst_size,
            took=result.took,
            error=result.error,
        )
        self.add(entry)

    def get_all(self) -> list[dict]:
        """Вернуть все записи (самые свежие первые)."""
        with self._mutex:
            return self._load()

    def clear(self) -> None:
        """Очистить историю."""
        with self._mutex:
            if HISTORY_FILE.exists():
                HISTORY_FILE.unlink()

    def _load(self) -> list[dict]:
        if HISTORY_FILE.exists():
            try:
                data = json.loads(HISTORY_FILE.read_text("utf-8"))
                if isinstance(data, list):
                    return data
            except (json.JSONDecodeError, OSError):
                pass
        return []

    def _save(self, entries: list[dict]):
        HISTORY_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=1), "utf-8")


# ──────────────────────────────────────────────────────────────────────────────
# ConfigManager — сохраняет настройки между запусками
# ──────────────────────────────────────────────────────────────────────────────


class ConfigManager:
    """Постоянные настройки приложения: последняя папка вывода, сортировка и т.д.

    Хранится в JSON рядом с историей:
      Linux:   ~/.config/conv/config.json
      Windows: %APPDATA%\conv\config.json
    """

    DEFAULTS: dict = {
        "last_output_dir": "",
        "sort_by_type": False,
    }

    def __init__(self):
        self._path = _config_dir() / CONFIG_FILE_NAME
        self._data: dict = dict(self.DEFAULTS)
        self._load()

    # ── Свойства ──────────────────────────────────────────────────────

    @property
    def last_output_dir(self) -> str:
        return self._data.get("last_output_dir", "")

    @last_output_dir.setter
    def last_output_dir(self, value: str) -> None:
        self._data["last_output_dir"] = str(value)
        self._save()

    @property
    def sort_by_type(self) -> bool:
        return self._data.get("sort_by_type", False)

    @sort_by_type.setter
    def sort_by_type(self, value: bool) -> None:
        self._data["sort_by_type"] = bool(value)
        self._save()

    # ── Внутреннее ────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._path.exists():
            try:
                stored = json.loads(self._path.read_text("utf-8"))
                if isinstance(stored, dict):
                    self._data.update(stored)
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, ensure_ascii=False, indent=1), "utf-8")


__all__ = [
    "HistoryEntry",
    "HistoryManager",
    "ConfigManager",
]
