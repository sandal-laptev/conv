"""История конвертаций — JSON-лог в ~/.conv/history.json."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

HISTORY_FILE = Path.home() / ".conv" / "history.json"
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
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

    def add(self, entry: HistoryEntry):
        """Добавить запись и сохранить."""
        with self._mutex:
            entries = self._load()
            entries.insert(0, asdict(entry))
            if len(entries) > self._max:
                entries = entries[:self._max]
            self._save(entries)

    def add_from_result(self, result, operation: str):
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

    def clear(self):
        """Очистить историю."""
        with self._mutex:
            if HISTORY_FILE.exists():
                HISTORY_FILE.unlink()

    def _load(self) -> list[dict]:
        if HISTORY_FILE.exists():
            try:
                data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
            except (json.JSONDecodeError, OSError):
                pass
        return []

    def _save(self, entries: list[dict]):
        HISTORY_FILE.write_text(
            json.dumps(entries, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
