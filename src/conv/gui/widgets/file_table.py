"""Таблица файлов — QTreeView с чекбоксами, сортировкой и контекстным меню."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QPainter,
    QPen,
    QStandardItem,
    QStandardItemModel,
)
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QMenu,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from conv.core import AUDIO_INPUT, VIDEO_INPUT, ConvertResult, _fmt_size as fmt_size
from conv.gui.i18n import _


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


COL_CHECK = 0
COL_NAME = 1
COL_SIZE = 2
COL_FORMAT = 3
COL_STATUS = 4
COL_RESULT = 5

HEADERS = ["", _("col_file"), _("col_size"), _("col_format"), _("col_status"), _("col_result")]


class FileTableWidget(QWidget):
    """Таблица файлов с чекбоксами, сортировкой, дропом и контекстным меню."""

    file_clicked = Signal(int)
    selection_changed = Signal()
    remove_requested = Signal(object)  # list[Path]
    files_dropped = Signal(object)     # list[Path]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paths: list[Path] = []
        self._results: dict[Path, ConvertResult] = {}
        self._target_format: str = ""
        self._drag_over = False
        self._check_states: dict[Path, bool] = {}  # true = checked
        self._build_ui()
        self.setAcceptDrops(True)

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
        self._tree.setVisible(False)

        header = self._tree.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(COL_CHECK, QHeaderView.Fixed)
        header.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_SIZE, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_FORMAT, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_RESULT, QHeaderView.Stretch)
        self._tree.setColumnWidth(COL_CHECK, 30)

        self._tree.setStyleSheet("""
            QTreeView::item:hover { background-color: rgba(0, 210, 255, 30); }
            QTreeView::indicator {
                width: 14px; height: 14px;
                border: 1px solid #2a2a4e;
                border-radius: 3px;
                background-color: #16213e;
            }
            QTreeView::indicator:checked {
                background-color: #00e676;
                border: 1px solid #00e676;
            }
            QTreeView::indicator:hover { border-color: #00d2ff; }
        """)

        # Подсказка при пустом списке
        self._drop_hint = QLabel()
        self._drop_hint.setAlignment(Qt.AlignCenter)
        self._drop_hint.setText(
            "📂  Перетащите файлы сюда\n\n"
            "или нажмите «Выбрать файлы» сверху"
        )
        self._drop_hint.setStyleSheet("""
            color: #606070;
            font-size: 15px;
            padding: 40px;
            border: 2px dashed #2a2a4e;
            border-radius: 12px;
            background-color: rgba(22, 33, 62, 80);
        """)
        self._drop_hint.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._drop_hint.setVisible(True)
        layout.addWidget(self._drop_hint, stretch=1)
        layout.addWidget(self._tree, stretch=1)

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
    def current_path(self) -> Path | None:
        """Файл под синим выделением (фокус-строка)."""
        idx = self._tree.currentIndex()
        if idx.isValid() and 0 <= idx.row() < len(self._paths):
            return self._paths[idx.row()]
        return None

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
        state = Qt.Checked if checked else Qt.Unchecked
        for i, p in enumerate(self._paths):
            item = self._model.item(i, COL_CHECK)
            if item:
                item.setCheckState(state)
                self._check_states[p] = checked
        self.selection_changed.emit()

    def invert_selection(self) -> None:
        for i, p in enumerate(self._paths):
            item = self._model.item(i, COL_CHECK)
            if item:
                new = item.checkState() != Qt.Checked
                item.setCheckState(Qt.Checked if new else Qt.Unchecked)
                self._check_states[p] = new
        self.selection_changed.emit()

    # ── Управление файлами ─────────────────────────────────────────────

    def retranslate(self) -> None:
        """Обновить заголовки при смене языка."""
        HEADERS[COL_NAME] = _("col_file")
        HEADERS[COL_SIZE] = _("col_size")
        HEADERS[COL_FORMAT] = _("col_format")
        HEADERS[COL_STATUS] = _("col_status")
        HEADERS[COL_RESULT] = _("col_result")
        self._model.setHorizontalHeaderLabels(HEADERS)
        # Обновить подсказку дропа
        self._drop_hint.setText(f"{_('drop_hint')}\n\n{_('drop_hint_sub')}")

    def set_target_format(self, fmt: str) -> None:
        self._target_format = fmt
        self._rebuild()

    def set_files(self, paths: list[Path]) -> None:
        self._paths = list(paths)
        self._results.clear()
        self._check_states.clear()
        self._rebuild()

    def add_files(self, paths: list[Path]) -> None:
        existing = set(self._paths)
        for p in paths:
            if p not in existing:
                self._paths.append(p)
                existing.add(p)
                # новые файлы — отмечены
                self._check_states[p] = True
        self._rebuild()

    def remove_files(self, paths: list[Path]) -> None:
        removals = set(paths)
        self._paths = [p for p in self._paths if p not in removals]
        for p in removals:
            self._results.pop(p, None)
            self._check_states.pop(p, None)
        self._rebuild()
        if removals:
            self.remove_requested.emit(list(removals))

    def clear(self) -> None:
        self._paths.clear()
        self._results.clear()
        self._check_states.clear()
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

    # ── Drag-n-Drop ─────────────────────────────────────────────────────

    def _show_drag_border(self, show: bool):
        self._drag_over = show
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._drag_over:
            p = QPainter(self)
            p.setPen(QPen(QColor("#00d2ff"), 3, Qt.DashLine))
            p.drawRoundedRect(self.rect().adjusted(3, 3, -3, -3), 8, 8)
            p.end()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._show_drag_border(True)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._show_drag_border(False)

    def dropEvent(self, event: QDropEvent):
        self._show_drag_border(False)
        if not event.mimeData().hasUrls():
            return
        paths: list[Path] = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                p = Path(url.toLocalFile())
                if p.exists():
                    paths.append(p)
        if not paths:
            return
        event.acceptProposedAction()
        from conv.core import Converter as _Conv
        collected = _Conv().collect(paths, recursive=True)
        if collected:
            self.add_files(collected)
            self.files_dropped.emit(collected)

    # ── Построение ─────────────────────────────────────────────────────

    def _rebuild(self):
        self._model.removeRows(0, self._model.rowCount())
        has_files = len(self._paths) > 0
        self._drop_hint.setVisible(not has_files)
        self._tree.setVisible(has_files)
        if has_files:
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
            info = (
                f"{fmt_size(res.dst_size)} ({res.dst_size / res.src_size * 100:.0f}%) — {res.fmt_took()}"
                if res.src_size else "готово"
            )
        elif res and not res.ok:
            status = "❌"
            info = res.error[:50]
        else:
            status = "⏳"
            info = ""

        # Восстанавливаем состояние чекбокса
        checked = self._check_states.get(path, True)

        check_item = QStandardItem()
        check_item.setCheckable(True)
        check_item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
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
            # Сохраняем состояние чекбокса
            row = index.row()
            if 0 <= row < len(self._paths):
                item = self._model.item(row, COL_CHECK)
                if item:
                    self._check_states[self._paths[row]] = (item.checkState() == Qt.Checked)
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

        act_toggle = QAction(
            "✅ Снять" if self._is_checked(row) else "✅ Выделить", self._tree)
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

        # Удаление по правому клику — только этот файл
        act_remove_this = QAction("🗑 Удалить файл", self._tree)
        act_remove_this.triggered.connect(lambda: self._remove_file(path))
        menu.addAction(act_remove_this)

        act_remove_sel = QAction(
            f"🗑 Удалить выделенные чекбоксом ({len(self.selected_paths)})", self._tree)
        act_remove_sel.triggered.connect(
            lambda: self.remove_files(self.selected_paths))
        menu.addAction(act_remove_sel)

        menu.addSeparator()

        from conv.core import OUTPUT_FORMATS
        fmt_menu = menu.addMenu("🎞 Задать формат выделенным")
        act_auto = QAction("Авто", self._tree)
        act_auto.triggered.connect(lambda: None)
        fmt_menu.addAction(act_auto)
        for key, val in OUTPUT_FORMATS.items():
            act = QAction(f".{key} — {val['desc']}", self._tree)
            act.triggered.connect(lambda k=key: None)
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
            if 0 <= row < len(self._paths):
                self._check_states[self._paths[row]] = (new_state == Qt.Checked)
            self.selection_changed.emit()

    def _remove_file(self, path: Path) -> None:
        """Удалить один файл по прямому пути (из контекстного меню)."""
        self.remove_files([path])
