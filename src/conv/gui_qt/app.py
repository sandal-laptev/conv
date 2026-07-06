"""Главное окно ConvApp — QMainWindow."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import QSplitter
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from conv.core import Converter, ConvertRequest, _fmt_size as fmt_size
from conv.gui_qt.controllers.conversion import ConversionWorker
from conv.gui_qt.theme import COLORS
from conv.gui_qt.widgets.file_table import FileTableWidget
from conv.gui_qt.widgets.preview import PreviewPanel
from conv.gui_qt.widgets.params import ParamsWidget
from conv.history import HistoryManager, ConfigManager
from conv.logger import get_logger, tail as log_tail

log = get_logger("conv.gui_qt")

# re-export для краткости
from conv.core import _fmt_time as _fmt_time


class ConvApp(QMainWindow):
    """Главное окно приложения (Qt6)."""

    def __init__(self):
        super().__init__()

        self.converter = Converter()
        self.history = HistoryManager()
        self.config = ConfigManager()

        self._worker: Optional[ConversionWorker] = None
        self._thread: Optional[QThread] = None

        self._setup_window()
        self._build_ui()
        self._apply_config()
        self._setup_shortcuts()

        log.info("Qt GUI запущен")

    # ── Окно ───────────────────────────────────────────────────────────

    def _setup_window(self):
        self.setWindowTitle("🖧 conv — Иохим Кузьмич Media Converter")
        self.resize(1100, 720)
        self.setMinimumSize(700, 600)

    # ── Сборка UI ──────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(6)

        # Хедер
        header = QLabel("🖧  conv  —  Иохим Кузьмич Media Converter")
        header.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {COLORS['accent']};")
        layout.addWidget(header)

        # Панель инструментов
        layout.addLayout(self._build_toolbar())

        # Параметры
        self.params = ParamsWidget()
        self.params.format_changed.connect(self._on_format_changed)
        layout.addWidget(self.params)

        # Выходная папка
        layout.addLayout(self._build_output_row())

        # Контент: таблица файлов + превью
        content = QSplitter(Qt.Horizontal)

        self.file_table = FileTableWidget()
        self.file_table.file_clicked.connect(self._on_file_click)
        self.file_table.files_dropped.connect(lambda _: self._update_buttons())
        # Привязка кнопок выделения (созданы в _build_toolbar)
        self._btn_select_all.clicked.connect(
            lambda: self.file_table.set_all_checked(True))
        self._btn_select_none.clicked.connect(
            lambda: self.file_table.set_all_checked(False))
        self._btn_invert.clicked.connect(self.file_table.invert_selection)
        content.addWidget(self.file_table)

        self.preview = PreviewPanel()
        self.preview.prev_clicked.connect(self._preview_prev)
        self.preview.next_clicked.connect(self._preview_next)
        content.addWidget(self.preview)

        content.setStretchFactor(0, 3)
        content.setStretchFactor(1, 2)
        content.setSizes([660, 440])

        layout.addWidget(content, stretch=1)

        # Нижняя панель: прогресс + кнопка конвертации + статус
        layout.addLayout(self._build_bottom())

    def _build_toolbar(self):
        hbox = QHBoxLayout()
        hbox.setSpacing(6)

        self._btn_select = QPushButton("📂 Выбрать файлы")
        self._btn_select.clicked.connect(self._select_files)
        hbox.addWidget(self._btn_select)

        self._btn_select_dir = QPushButton("📁 Выбрать папку (рекурсивно)")
        self._btn_select_dir.clicked.connect(self._select_folder)
        hbox.addWidget(self._btn_select_dir)

        self._btn_clear = QPushButton("🗑 Очистить")
        self._btn_clear.clicked.connect(self._clear_all)
        self._btn_clear.setEnabled(False)
        hbox.addWidget(self._btn_clear)

        hbox.addSpacing(12)

        self._btn_select_all = QPushButton("✅ Всё")
        self._btn_select_all.setEnabled(False)
        hbox.addWidget(self._btn_select_all)

        self._btn_select_none = QPushButton("❌ Снять")
        self._btn_select_none.setEnabled(False)
        hbox.addWidget(self._btn_select_none)

        self._btn_invert = QPushButton("🔀 Инверт.")
        self._btn_invert.setEnabled(False)
        hbox.addWidget(self._btn_invert)

        hbox.addStretch()

        # Инструменты
        self._btn_tools = QPushButton("🔧 Проверить")
        self._btn_tools.clicked.connect(self._check_tools)
        hbox.addWidget(self._btn_tools)

        self._btn_logs = QPushButton("📋 Логи")
        self._btn_logs.clicked.connect(self._copy_logs)
        hbox.addWidget(self._btn_logs)

        self._btn_history = QPushButton("📜 История")
        # self._btn_history.clicked.connect(self._show_history)
        hbox.addWidget(self._btn_history)

        return hbox

    def _build_output_row(self):
        hbox = QHBoxLayout()
        hbox.setSpacing(8)

        hbox.addWidget(QLabel("📁 Выход:"))

        self._out_dir_edit = QLineEdit()
        self._out_dir_edit.setText(str(Path.cwd() / "CONVERTED"))
        self._out_dir_edit.setMinimumWidth(350)
        hbox.addWidget(self._out_dir_edit, stretch=1)

        btn_browse = QPushButton("📂")
        btn_browse.setFixedWidth(30)
        btn_browse.clicked.connect(self._browse_output_dir)
        hbox.addWidget(btn_browse)

        hbox.addStretch()
        return hbox

    def _build_bottom(self):
        layout = QVBoxLayout()
        layout.setSpacing(4)

        # Прогресс
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        layout.addWidget(self._progress)

        # Ряд: кнопка + статус + статистика
        row = QHBoxLayout()
        row.setSpacing(8)

        self._btn_convert = QPushButton("⚡ Конвертировать")
        self._btn_convert.setStyleSheet(
            f"background-color: {COLORS['accent']}; color: {COLORS['bg']}; "
            f"font-weight: bold; padding: 6px 20px;"
        )
        self._btn_convert.clicked.connect(self._do_convert)
        self._btn_convert.setEnabled(False)
        row.addWidget(self._btn_convert)

        self._btn_open = QPushButton("📂 Открыть папку")
        self._btn_open.clicked.connect(self._open_output)
        self._btn_open.setEnabled(False)
        row.addWidget(self._btn_open)

        self._status_label = QLabel("Ожидание файлов...")
        self._status_label.setStyleSheet(f"color: {COLORS['text2']};")
        row.addWidget(self._status_label, stretch=1)

        self._stats_label = QLabel("")
        self._stats_label.setStyleSheet(f"color: {COLORS['text3']};")
        row.addWidget(self._stats_label)

        layout.addLayout(row)
        return layout

    # ── Файлы ──────────────────────────────────────────────────────────

    def _select_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выберите файлы для конвертации",
            "",
            "Медиафайлы (*.jpg *.jpeg *.png *.webp *.bmp *.tiff *.heic *.heif "
            "*.svg *.svgz *.mp4 *.avi *.mkv *.mov *.wmv *.webm "
            "*.mp3 *.wav *.flac *.ogg *.m4a *.opus *.aac);;Все файлы (*)",
        )
        if files:
            paths = [Path(f) for f in files]
            self.file_table.add_files(paths)
            self._update_buttons()

    def _select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку (рекурсивно)")
        if folder:
            paths = self.converter.collect([Path(folder)], recursive=True)
            if paths:
                self.file_table.add_files(paths)
                self._update_buttons()
            else:
                self._status_label.setText("⚠ Нет конвертируемых файлов в папке")

    def _clear_all(self):
        self.file_table.clear()
        self.preview.clear()
        self._progress.setValue(0)
        self._status_label.setText("Ожидание файлов...")
        self._stats_label.setText("")
        self._update_buttons()

    def _update_buttons(self):
        has_files = self.file_table.count > 0
        busy = self._worker is not None
        self._btn_convert.setEnabled(has_files and not busy)
        self._btn_clear.setEnabled(has_files and not busy)
        self._btn_select.setEnabled(not busy)
        self._btn_select_dir.setEnabled(not busy)
        self._btn_select_all.setEnabled(has_files and not busy)
        self._btn_select_none.setEnabled(has_files and not busy)
        self._btn_invert.setEnabled(has_files and not busy)

    # ── Выходная папка ─────────────────────────────────────────────────

    def _browse_output_dir(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Выберите папку для сохранения",
            self._out_dir_edit.text(),
        )
        if folder:
            self._out_dir_edit.setText(folder)
            self.config.last_output_dir = folder

    def _open_output(self):
        out_dir = Path(self._out_dir_edit.text())
        if out_dir.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(out_dir)))

    # ── Формат ─────────────────────────────────────────────────────────

    def _on_format_changed(self):
        self.file_table.set_target_format(self.params.format_name)
        # Обновить превью если есть активный файл
        if self.preview.current_path:
            paths = self.file_table.paths
            cur = self.preview.current_path
            if cur in paths:
                idx = paths.index(cur)
                self._show_preview(idx)

    # ── Клик по файлу / навигация ─────────────────────────────────────

    def _on_file_click(self, idx: int):
        self._show_preview(idx)

    def _preview_prev(self):
        paths = self.file_table.paths
        cur = self.preview.current_path
        if cur and cur in paths:
            idx = paths.index(cur) - 1
            if idx >= 0:
                self._show_preview(idx)

    def _preview_next(self):
        paths = self.file_table.paths
        cur = self.preview.current_path
        if cur and cur in paths:
            idx = paths.index(cur) + 1
            if idx < len(paths):
                self._show_preview(idx)

    def _show_preview(self, idx: int):
        paths = self.file_table.paths
        if 0 <= idx < len(paths):
            self.preview.show(
                path=paths[idx],
                idx=idx,
                total=len(paths),
                fmt_var=self.params.format_name,
                quality=self.params.quality,
                max_size=self.params.max_size,
            )

    # ── Конвертация ────────────────────────────────────────────────────

    def _do_convert(self):
        if self.file_table.count == 0:
            return

        # Определяем список файлов: выделенные или все
        paths = self.file_table.selected_paths
        if not paths:
            self._status_label.setText("⚠ Нет выделенных файлов для конвертации")
            return

        self.file_table.reset_results()
        self._btn_open.setEnabled(False)

        # ── Режим переименования ──
        if self.params.rename_only:
            ext = self.params.format_name
            if not ext:
                self._status_label.setText("⚠ Выберите формат для переименования")
                return
            self._status_label.setText(f"⏳ Переименование в .{ext}...")
            self._progress.setValue(0)
            self._set_busy(True)

            results = self.converter.rename_many(
                paths, ext,
                on_progress=lambda d, t, r: self._progress.setValue(int(d / t * 100)),
            )
            for r in results:
                self.file_table.set_result(r.request.input_path, r)

            ok = sum(1 for r in results if r.ok)
            fail = len(results) - ok
            self._status_label.setText(
                f"✅ Переименовано: {ok}" if fail == 0
                else f"✅ {ok}  ❌ {fail}"
            )
            self._progress.setValue(100)
            self._set_busy(False)
            for r in results:
                self.history.add_from_result(r, "Переименование")
            return

        # ── Обычная конвертация ──
        out_dir = Path(self._out_dir_edit.text())
        out_dir.mkdir(parents=True, exist_ok=True)

        requests = [
            ConvertRequest(
                p, out_dir,
                output_format=self.params.format_name,
                quality=self.params.quality,
                max_size=self.params.max_size,
                sort_by_type=self.params.sort_by_type,
                trim_start=self.preview.get_trim(p)[0],
                trim_end=self.preview.get_trim(p)[1],
            )
            for p in paths
        ]

        self._status_label.setText("⏳ Конвертация...")
        self._progress.setValue(0)
        self._set_busy(True)
        self._btn_convert.setText("⏹ Отмена")
        self._btn_convert.setStyleSheet(
            f"background-color: {COLORS['error']}; color: white; "
            f"font-weight: bold; padding: 6px 20px;"
        )
        self._btn_convert.clicked.disconnect()
        self._btn_convert.clicked.connect(self._cancel_convert)

        self._worker = ConversionWorker(self.converter, requests)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.file_done.connect(self._on_file_done)
        self._worker.finished.connect(self._on_finish)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    def _cancel_convert(self):
        if self._worker:
            self._worker.cancel()
            self._status_label.setText("⏹ Отмена...")

    def _set_busy(self, busy: bool):
        self._btn_select.setEnabled(not busy)
        self._btn_select_dir.setEnabled(not busy)
        self._btn_clear.setEnabled(not busy and self.file_table.count > 0)
        self._btn_select_all.setEnabled(not busy and self.file_table.count > 0)
        self._btn_select_none.setEnabled(not busy and self.file_table.count > 0)
        self._btn_invert.setEnabled(not busy and self.file_table.count > 0)

    def _on_progress(self, done: int, total: int, elapsed: float, eta: float):
        self._progress.setValue(int(done / total * 100))
        self._status_label.setText(
            f"⏳ {done}/{total}  ({_fmt_time(elapsed)} / ~{_fmt_time(eta)})"
        )

    def _on_file_done(self, result):
        self.file_table.set_result(result.request.input_path, result)

    def _on_finish(self, results, cancelled: bool):
        ok = sum(1 for r in results if r.ok)
        total = len(results)
        fail = total - ok

        if cancelled and ok == 0:
            self._status_label.setText("⏹ Отменено")
        elif fail == 0:
            self._status_label.setText(f"✅ Готово: {ok}/{total}")
            self._btn_open.setEnabled(ok > 0)
        else:
            self._status_label.setText(f"✅ {ok}/{total}  ❌ {fail}/{total}")
            self._btn_open.setEnabled(ok > 0)

        # Статистика
        total_src = sum(r.src_size for r in results)
        total_dst = sum(r.dst_size for r in results if r.ok)
        total_time = sum(r.took for r in results)
        if total_src > 0:
            pct = total_dst / total_src * 100 if total_dst > 0 else 0
            self._stats_label.setText(
                f"📦 {fmt_size(total_src)} → {fmt_size(total_dst)} "
                f"({pct:.0f}%)  ⏱ {_fmt_time(total_time)}"
            )

        self._progress.setValue(100 if ok > 0 else 0)
        self._btn_convert.setText("⚡ Конвертировать")
        self._btn_convert.setStyleSheet(
            f"background-color: {COLORS['accent']}; color: {COLORS['bg']}; "
            f"font-weight: bold; padding: 6px 20px;"
        )
        self._btn_convert.clicked.disconnect()
        self._btn_convert.clicked.connect(self._do_convert)
        self._set_busy(False)
        self._update_buttons()

        # Сохраняем в историю
        for r in results:
            self.history.add_from_result(r, "Конвертация")

        # Сохраняем настройки
        self.config.last_output_dir = self._out_dir_edit.text()
        self.config.sort_by_type = self.params.sort_by_type

        self._worker = None
        self._thread = None

        log.info("Конвертация завершена: %d/%d успешно", ok, total)

    # ── Инструменты ────────────────────────────────────────────────────

    def _check_tools(self):
        tools = self.converter.check_tools()
        labels = {
            "ffmpeg": "ffmpeg (конвертация)",
            "ffprobe": "ffprobe (медиа-инфо)",
            "rsvg_convert": "rsvg-convert (SVG)",
            "pil": "Pillow (изображения)",
            "pillow_heif": "pillow-heif (HEIC/HEIF)",
        }
        lines = [
            f"  {'✅' if tools.get(k) else '❌'}  {label}"
            for k, label in labels.items()
        ]
        msg = "Доступные инструменты:\n\n" + "\n".join(lines)

        missing = [k for k, v in tools.items() if not v]
        if missing:
            tips = {
                "ffmpeg": "apt install ffmpeg",
                "rsvg_convert": "apt install librsvg2-bin",
                "pil": "pip install Pillow",
                "pillow_heif": "pip install pillow-heif",
            }
            msg += "\n\n⚠ Отсутствуют:\n" + "\n".join(
                f"  {k}: {tips.get(k, '?')}" for k in missing
            )

        QMessageBox.information(self, "🔧 Проверка инструментов", msg)
        log.info("Проверка инструментов: %s", tools)

    def _copy_logs(self):
        lines = log_tail(80)
        QApplication.clipboard().setText(lines)
        orig = self._btn_logs.text()
        self._btn_logs.setText("✅ Скопировано!")
        threading.Timer(
            2.0, lambda: self._btn_logs.setText(orig),
        ).start()
        log.info("Логи скопированы в буфер")

    # ── Горячие клавиши ───────────────────────────────────────────────

    def _setup_shortcuts(self):
        _sc = lambda *a, **kw: QShortcut(*a, **kw, context=Qt.ApplicationShortcut, parent=self)

        _sc(QKeySequence("Ctrl+A")).activated.connect(
            lambda: self.file_table.set_all_checked(True))
        _sc(QKeySequence("Ctrl+Shift+A")).activated.connect(
            lambda: self.file_table.set_all_checked(False))
        _sc(QKeySequence("Ctrl+I")).activated.connect(
            self.file_table.invert_selection)
        _sc(QKeySequence("Delete")).activated.connect(self._delete_selected)
        _sc(QKeySequence("Return")).activated.connect(self._do_convert)
        _sc(QKeySequence("Ctrl+O")).activated.connect(self._select_files)
        _sc(QKeySequence("Ctrl+Shift+O")).activated.connect(self._select_folder)
        _sc(QKeySequence("Ctrl+.")).activated.connect(self._open_output)
        _sc(QKeySequence("Escape")).activated.connect(self._cancel_or_clear)
        _sc(QKeySequence( "Space")).activated.connect(self._toggle_playback)

        log.info("Горячие клавиши: Ctrl+A/Shift+A/I/Delete/Enter/Ctrl+O/Space/Esc")

    def _delete_selected(self):
        """Удалить выделенные файлы (Delete)."""
        sel = self.file_table.selected_paths
        if sel:
            self.file_table.remove_files(sel)
            self._update_buttons()
            self.preview.clear()

    def _cancel_or_clear(self):
        """Esc: отменить конвертацию или очистить список."""
        if self._worker is not None:
            self._cancel_convert()
        elif self.file_table.count > 0:
            self._clear_all()

    def _toggle_playback(self):
        """Space: play/pause видео."""
        if hasattr(self, "preview"):
            self.preview.toggle_video_playback()

    # ── Конфиг ─────────────────────────────────────────────────────────

    def _apply_config(self):
        if self.config.last_output_dir:
            self._out_dir_edit.setText(self.config.last_output_dir)
        self.params.sort_by_type = self.config.sort_by_type
