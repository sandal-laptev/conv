"""Таблица файлов — QTreeView с чекбоксами, сортировкой и контекстным меню."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QHeaderView,
    QMenu,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from conv.core import AUDIO_INPUT, VIDEO_INPUT, ConvertResult, _fmt_size as fmt_size


def _file_icon(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in VIDEO_INPUT:
        return "🎬"
    if ext in AUDIO_INPUT:
        return "🎵"
    return "🖼"


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


# Колонки
COL_CHECK = 0
COL_NAME = 1
COL_SIZE = 2
COL_FORMAT = 3
COL_STATUS = 4
COL_RESULT = 5

HEADERS = ["", "Файл", "Размер", "→ формат", "Статус", "Результат"]


class FileTableWidget(QWidget):
    """Таблица файлов с чекбоксами и сортировкой.

    Сигналы:
      file_clicked(idx)   — клик по имени файла
      selection_changed() — любой чекбокс изменился
      remove_requested(paths) — удалить файлы из списка
    """

    file_clicked = Signal(int)
    selection_changed = Signal()
    remove_requested = Signal(object)  # list[Path]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paths: list[Path] = []
        self._results: dict[Path, ConvertResult] = {}
        self._target_format: str = ""
        self._build_ui()

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
        self._tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        self._tree.clicked.connect(self._on_click)

        header = self._tree.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(COL_CHECK, QHeaderView.Fixed)
        header.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_SIZE, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_FORMAT, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_RESULT, QHeaderView.Stretch)
        self._tree.setColumnWidth(COL_CHECK, 30)

        # Ховер подсветка всей строки
        self._tree.setStyleSheet("""
            QTreeView::item:hover { background-color: rgba(0, 210, 255, 30); }
        """)

        layout.addWidget(self._tree)

    # ── Свойства ───────────────────────────────────────────────────────

    @property
    def paths(self) -> list[Path]:
        return self._paths.copy()

    @property
    def count(self) -> int:
        return len(self._paths)

    @property
    def results(self) -> dict[Path, ConvertResult]:
        return self._results

    @property
    def selected_paths(self) -> list[Path]:
        """Файлы с отмеченными чекбоксами."""
        return [p for i, p in enumerate(self._paths)
                if self._model.item(i, COL_CHECK) and
                self._model.item(i, COL_CHECK).checkState() == Qt.Checked]

    @property
    def all_checked(self) -> bool:
        return all(
            self._model.item(i, COL_CHECK).checkState() == Qt.Checked
            for i in range(self._model.rowCount())
        ) if self._model.rowCount() > 0 else False

    def set_all_checked(self, checked: bool) -> None:
        """Отметить/снять все чекбоксы."""
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(self._model.rowCount()):
            self._model.item(i, COL_CHECK).setCheckState(state)
        self.selection_changed.emit()

    # ── Управление файлами ─────────────────────────────────────────────

    def set_target_format(self, fmt: str) -> None:
        self._target_format = fmt
        self._rebuild()

    def set_files(self, paths: list[Path]) -> None:
        self._paths = list(paths)
        self._results.clear()
        self._rebuild()

    def add_files(self, paths: list[Path]) -> None:
        existing = set(self._paths)
        for p in paths:
            if p not in existing:
                self._paths.append(p)
                existing.add(p)
        self._rebuild()

    def remove_files(self, paths: list[Path]) -> None:
        removals = set(paths)
        self._paths = [p for p in self._paths if p not in removals]
        for p in removals:
            self._results.pop(p, None)
        self._rebuild()

    def clear(self) -> None:
        self._paths.clear()
        self._results.clear()
        self._rebuild()

    def set_result(self, path: Path, result: ConvertResult) -> None:
        self._results[path] = result
        for row, p in enumerate(self._paths):
            if p == path:
                self._update_row(row, p)
                break

    def reset_results(self) -> None:
        self._results.clear()
        self._rebuild()

    # ── Построение ─────────────────────────────────────────────────────

    def _rebuild(self):
        self._model.removeRows(0, self._model.rowCount())
        for p in self._paths:
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

        if res and res.ok:
            status = "✅"
            if res.src_size:
                info = f"{fmt_size(res.dst_size)} ({res.dst_size / res.src_size * 100:.0f}%) — {res.fmt_took()}"
            else:
                info = "готово"
        elif res and not res.ok:
            status = "❌"
            info = res.error[:50]
        else:
            status = "⏳"
            info = ""

        check_item = QStandardItem()
        check_item.setCheckable(True)
        check_item.setCheckState(Qt.Checked)  # по умолчанию отмечен
        check_item.setEditable(False)

        items = [
            check_item,
            self._item(f"{icon}  {path.name}"),
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

    # ── Клик ───────────────────────────────────────────────────────────

    def _on_click(self, index):
        col = index.column()
        if col == COL_CHECK:
            self.selection_changed.emit()
        else:
            row = index.row()
            if 0 <= row < len(self._paths):
                self.file_clicked.emit(row)

    # ── Контекстное меню ──────────────────────────────────────────────

    def _show_context_menu(self, pos):
        index = self._tree.indexAt(pos)
        if not index or index.row() < 0:
            return

        row = index.row()
        if row >= len(self._paths):
            return

        path = self._paths[row]
        menu = QMenu(self._tree)

        # Выделение
        act_toggle = QAction("✅ Выделить / Снять" if self._is_checked(row) else
                             "✅ Выделить", self._tree)
        act_toggle.triggered.connect(lambda: self._toggle_row(row))
        menu.addAction(act_toggle)

        menu.addSeparator()

        act_all = QAction("✅ Выделить все", self._tree)
        act_all.triggered.connect(lambda: self.set_all_checked(True))
        menu.addAction(act_all)

        act_none = QAction("❌ Снять всё", self._tree)
        act_none.triggered.connect(lambda: self.set_all_checked(False))
        menu.addAction(act_none)

        act_inv = QAction("🔀 Инвертировать", self._tree)
        act_inv.triggered.connect(self.invert_selection)
        menu.addAction(act_inv)

        menu.addSeparator()

        # Удаление
        act_remove_this = QAction("🗑 Удалить файл", self._tree)
        act_remove_this.triggered.connect(lambda: self.remove_files([path]))
        menu.addAction(act_remove_this)

        if self.selected_paths:
            act_remove_sel = QAction(
                f"🗑 Удалить выделенные ({len(self.selected_paths)})", self._tree)
            act_remove_sel.triggered.connect(
                lambda: self.remove_files(self.selected_paths))
            menu.addAction(act_remove_sel)

        menu.addSeparator()

        # Формат для выделенных
        from conv.core import OUTPUT_FORMATS
        fmt_menu = menu.addMenu("🎞 Задать формат выделенным")
        act_auto = QAction("Авто", self._tree)
        act_auto.triggered.connect(
            lambda: self._set_format_for_selected(""))
        fmt_menu.addAction(act_auto)
        for key, val in OUTPUT_FORMATS.items():
            act = QAction(f".{key} — {val['desc']}", self._tree)
            act.triggered.connect(lambda k=key: self._set_format_for_selected(k))
            fmt_menu.addAction(act)

        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _is_checked(self, row: int) -> bool:
        item = self._model.item(row, COL_CHECK)
        return item is not None and item.checkState() == Qt.Checked

    def _toggle_row(self, row: int) -> None:
        item = self._model.item(row, COL_CHECK)
        if item:
            new_state = Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked
            item.setCheckState(new_state)
            self.selection_changed.emit()

    def invert_selection(self) -> None:
        for i in range(self._model.rowCount()):
            item = self._model.item(i, COL_CHECK)
            if item:
                item.setCheckState(
                    Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)
        self.selection_changed.emit()

    def _set_format_for_selected(self, fmt: str) -> None:
        """Сигнал для внешней обработки (пока просто храним)."""
        # Пока не реализовано — в будущем можно задавать формат
        # для выделенных файлов через сигнал
        pass
