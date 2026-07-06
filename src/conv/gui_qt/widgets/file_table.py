"""Таблица файлов для конвертации — QTreeView с сортируемыми колонками."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QHeaderView, QTreeView, QVBoxLayout, QWidget

from conv.core import AUDIO_INPUT, VIDEO_INPUT, ConvertResult
from conv.core import _fmt_size as fmt_size


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _file_icon(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in VIDEO_INPUT:
        return "🎬"
    if ext in AUDIO_INPUT:
        return "🎵"
    return "🖼"


# Константы колонок
COL_ICON = 0
COL_NAME = 1
COL_SIZE = 2
COL_FORMAT = 3
COL_STATUS = 4
COL_RESULT = 5

HEADERS = ["", "Файл", "Размер", "→ формат", "Статус", "Результат"]


class FileTableWidget(QWidget):
    """Таблица файлов с колонками и поддержкой сортировки."""

    file_clicked = Signal(int)  # индекс

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paths: list[Path] = []
        self._results: dict[Path, ConvertResult] = {}
        self._target_format: str = ""

        self._build_ui()

    # ── Построение ─────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._model = QStandardItemModel(0, len(HEADERS))
        self._model.setHorizontalHeaderLabels(HEADERS)

        self._tree = QTreeView()
        self._tree.setModel(self._model)
        self._tree.setRootIsDecorated(False)
        self._tree.setAlternatingRowColors(True)
        self._tree.setSortingEnabled(True)
        self._tree.setSelectionMode(QTreeView.SingleSelection)
        self._tree.setSelectionBehavior(QTreeView.SelectRows)
        self._tree.setEditTriggers(QTreeView.NoEditTriggers)
        self._tree.setIndentation(0)
        self._tree.clicked.connect(self._on_click)

        # Настройка колонок
        header = self._tree.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(COL_ICON, QHeaderView.Fixed)
        header.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_SIZE, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_FORMAT, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_RESULT, QHeaderView.Stretch)
        self._tree.setColumnWidth(COL_ICON, 30)

        layout.addWidget(self._tree)

    # ── Публичное API ──────────────────────────────────────────────────

    @property
    def paths(self) -> list[Path]:
        return self._paths.copy()

    @property
    def count(self) -> int:
        return len(self._paths)

    @property
    def results(self) -> dict[Path, ConvertResult]:
        return self._results

    def set_target_format(self, fmt: str) -> None:
        """Обновить колонку целевого формата (пусто = авто)."""
        self._target_format = fmt
        self._rebuild()

    def set_files(self, paths: list[Path]) -> None:
        """Задать список файлов (заменяет текущий)."""
        self._paths = list(paths)
        self._results.clear()
        self._rebuild()

    def add_files(self, paths: list[Path]) -> None:
        """Добавить файлы."""
        existing = set(self._paths)
        for p in paths:
            if p not in existing:
                self._paths.append(p)
                existing.add(p)
        self._rebuild()

    def remove_file(self, path: Path) -> None:
        if path in self._paths:
            self._paths.remove(path)
            self._results.pop(path, None)
            self._rebuild()

    def clear(self) -> None:
        self._paths.clear()
        self._results.clear()
        self._rebuild()

    def set_result(self, path: Path, result: ConvertResult) -> None:
        self._results[path] = result
        # Живое обновление одной строки (без полной перестройки)
        for row, p in enumerate(self._paths):
            if p == path:
                self._update_row(row, p)
                break

    def reset_results(self) -> None:
        self._results.clear()
        self._rebuild()

    # ── Внутреннее ─────────────────────────────────────────────────────

    def _rebuild(self):
        self._model.removeRows(0, self._model.rowCount())
        for i, p in enumerate(self._paths):
            self._append_row(p)

    def _append_row(self, path: Path):
        row = self._model.rowCount()
        self._model.insertRow(row)
        self._update_row(row, path)

    def _update_row(self, row: int, path: Path):
        items = self._make_row_items(path)
        for col, item in enumerate(items):
            self._model.setItem(row, col, item)

    def _make_row_items(self, path: Path) -> list[QStandardItem]:
        from conv.core import resolve_format as resolve_fmt

        icon = _file_icon(path)
        target_fmt = self._target_format or resolve_fmt("", path.suffix)
        size_str = fmt_size(_file_size(path))

        res = self._results.get(path)

        # Статус и результат
        if res and res.ok:
            status = "✅"
            if res.src_size:
                info = (
                    f"{fmt_size(res.dst_size)} "
                    f"({res.dst_size / res.src_size * 100:.0f}%)"
                    f" — {res.fmt_took()}"
                )
            else:
                info = "готово"
        elif res and not res.ok:
            status = "❌"
            info = res.error[:50]
        else:
            status = "⏳"
            info = ""

        items = [
            self._item(icon, center=True),
            self._item(path.name),
            self._item(size_str, right=True),
            self._item(f".{target_fmt}", center=True),
            self._item(status, center=True),
            self._item(info),
        ]
        return items

    @staticmethod
    def _item(text: str, center: bool = False, right: bool = False) -> QStandardItem:
        item = QStandardItem(text)
        item.setEditable(False)
        if center:
            item.setTextAlignment(Qt.AlignCenter)
        elif right:
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return item

    def _on_click(self, index):
        row = index.row()
        if 0 <= row < len(self._paths):
            self.file_clicked.emit(row)
