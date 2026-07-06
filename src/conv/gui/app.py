"""Главное окно ConvApp — QMainWindow (MO Kolomyagi Media Converter)."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QIcon, QKeySequence, QShortcut
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
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from conv import __version__ as conv_version
from conv.core import Converter, ConvertRequest, ConvertResult, _fmt_size as fmt_size
from conv.gui.about import AboutDialog
from conv.gui.controllers.conversion import ConversionWorker
from conv.gui.i18n import _, set_lang
from conv.gui.theme import COLORS, apply_dark_theme, apply_light_theme, apply_system_theme
from conv.gui.widgets.file_table import FileTableWidget
from conv.gui.widgets.preview import PreviewPanel
from conv.gui.widgets.params import ParamsWidget
from conv.history import HistoryManager, ConfigManager
from conv.logger import get_logger, tail as log_tail

log = get_logger("conv.gui")

from conv.core import _fmt_time as _fmt_time


class ConvApp(QMainWindow):
    """Главное окно приложения (Qt6)."""

    def __init__(self):
        super().__init__()

        self.converter = Converter()
        self.history = HistoryManager()
        self.config = ConfigManager()

        self._worker: ConversionWorker | None = None
        self._thread: QThread | None = None

        # Применяем конфиг при старте
        set_lang(self.config.language)

        self._setup_window()
        self._build_ui()
        self._apply_config()
        self._setup_shortcuts()

        log.info("Qt GUI запущен")

    # ── Окно ───────────────────────────────────────────────────────────

    def _setup_window(self):
        self.setWindowTitle(_("window_title"))
        self.resize(1100, 720)
        self.setMinimumSize(700, 600)
        # Иконка окна
        ico = Path(__file__).resolve().parent / "resources" / "icon.png"
        if ico.exists():
            self.setWindowIcon(QIcon(str(ico)))

    # ── Сборка UI ──────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(6)

        # Хедер
        self._header = QLabel(_("header"))
        self._header.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {COLORS['accent']};")
        layout.addWidget(self._header)

        # Панель инструментов
        layout.addLayout(self._build_toolbar())

        # Параметры
        self.params = ParamsWidget()
        self.params.format_changed.connect(self._on_format_changed)
        layout.addWidget(self.params)

        # Выходная папка
        layout.addLayout(self._build_output_row())

        # Контент: таблица + превью
        content = QSplitter(Qt.Horizontal)

        self.file_table = FileTableWidget()
        self.file_table.file_clicked.connect(self._on_file_click)
        self.file_table.files_dropped.connect(lambda _: self._update_buttons())
        self.file_table.remove_requested.connect(self._on_files_removed)
        self._btn_select_all.clicked.connect(lambda: self.file_table.set_all_checked(True))
        self._btn_select_none.clicked.connect(lambda: self.file_table.set_all_checked(False))
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
        layout.addLayout(self._build_bottom())

    def _build_toolbar(self):
        hbox = QHBoxLayout()
        hbox.setSpacing(6)

        self._btn_select = QPushButton(_("btn_select_files"))
        self._btn_select.clicked.connect(self._select_files)
        hbox.addWidget(self._btn_select)

        self._btn_select_dir = QPushButton(_("btn_select_folder"))
        self._btn_select_dir.clicked.connect(self._select_folder)
        hbox.addWidget(self._btn_select_dir)

        self._btn_clear = QPushButton(_("btn_clear"))
        self._btn_clear.clicked.connect(self._clear_all)
        self._btn_clear.setEnabled(False)
        hbox.addWidget(self._btn_clear)

        hbox.addSpacing(12)

        self._btn_select_all = QPushButton(_("btn_select_all"))
        self._btn_select_all.setEnabled(False)
        hbox.addWidget(self._btn_select_all)

        self._btn_select_none = QPushButton(_("btn_deselect_all"))
        self._btn_select_none.setEnabled(False)
        hbox.addWidget(self._btn_select_none)

        self._btn_invert = QPushButton(_("btn_invert"))
        self._btn_invert.setEnabled(False)
        hbox.addWidget(self._btn_invert)

        hbox.addStretch()

        # Язык
        self._btn_lang = QPushButton("🇬🇧 EN" if self.config.language == "ru" else "🇷🇺 RU")
        self._btn_lang.setFixedWidth(60)
        self._btn_lang.clicked.connect(self._toggle_language)
        hbox.addWidget(self._btn_lang)

        # Тема
        theme_labels = {"dark": "🌙", "light": "☀️", "system": "💻"}
        self._btn_theme = QPushButton(theme_labels.get(self.config.theme, "🌙"))
        self._btn_theme.setFixedWidth(36)
        self._btn_theme.clicked.connect(self._toggle_theme)
        hbox.addWidget(self._btn_theme)

        # Инструменты
        self._btn_tools = QPushButton(_("btn_check_tools"))
        self._btn_tools.clicked.connect(self._check_tools)
        hbox.addWidget(self._btn_tools)

        self._btn_logs = QPushButton(_("btn_logs"))
        self._btn_logs.clicked.connect(self._copy_logs)
        hbox.addWidget(self._btn_logs)

        # About
        self._btn_about = QPushButton(_("btn_about"))
        self._btn_about.clicked.connect(self._show_about)
        hbox.addWidget(self._btn_about)

        return hbox

    def _build_output_row(self):
        hbox = QHBoxLayout()
        hbox.setSpacing(8)
        self._out_label = QLabel(_("output_label"))
        hbox.addWidget(self._out_label)
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

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        layout.addWidget(self._progress)

        row = QHBoxLayout()
        row.setSpacing(8)

        self._btn_convert = QPushButton(_("btn_convert"))
        self._btn_convert.setStyleSheet(
            f"background-color: {COLORS['accent']}; color: {COLORS['bg']}; "
            f"font-weight: bold; padding: 6px 20px;"
        )
        self._btn_convert.clicked.connect(self._do_convert)
        self._btn_convert.setEnabled(False)
        row.addWidget(self._btn_convert)

        self._btn_open = QPushButton(_("btn_open_folder"))
        self._btn_open.clicked.connect(self._open_output)
        self._btn_open.setEnabled(False)
        row.addWidget(self._btn_open)

        self._status_label = QLabel(_("status_waiting"))
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
            self, "Выберите файлы", "",
            "Медиафайлы (*.jpg *.jpeg *.png *.webp *.bmp *.tiff *.heic *.heif "
            "*.svg *.svgz *.mp4 *.avi *.mkv *.mov *.wmv *.webm "
            "*.mp3 *.wav *.flac *.ogg *.m4a *.opus *.aac);;Все файлы (*)",
        )
        if files:
            self.file_table.add_files([Path(f) for f in files])
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
        self._status_label.setText(_("status_waiting"))
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
            self, "Выберите папку для сохранения", self._out_dir_edit.text())
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
        if self.preview.current_path:
            paths = self.file_table.paths
            cur = self.preview.current_path
            if cur in paths:
                idx = paths.index(cur)
                self._show_preview(idx)

    # ── Клик / навигация ───────────────────────────────────────────────

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
                path=paths[idx], idx=idx, total=len(paths),
                fmt_var=self.params.format_name,
                quality=self.params.quality,
                max_size=self.params.max_size,
            )

    # ── Конвертация ────────────────────────────────────────────────────

    def _do_convert(self):
        if self.file_table.count == 0:
            return
        paths = self.file_table.selected_paths
        if not paths:
            self._status_label.setText(_("status_no_selection"))
            return
        self.file_table.reset_results()
        self._btn_open.setEnabled(False)

        if self.params.rename_only:
            ext = self.params.format_name
            if not ext:
                self._status_label.setText(_("status_select_format"))
                return
            self._status_label.setText(f"{_('status_renaming')} .{ext}...")
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
                f"{_('status_renamed')} {ok}" if fail == 0 else f"✅ {ok}  ❌ {fail}")
            self._progress.setValue(100)
            self._set_busy(False)
            for r in results:
                self.history.add_from_result(r, "Переименование")
            return

        out_dir = Path(self._out_dir_edit.text())
        out_dir.mkdir(parents=True, exist_ok=True)
        audio_mode = self.params.audio_mode
        audio_fmt = self.params.audio_split_format

        # ── Split audio/video — отдельный поток ──
        if audio_mode == 'split':
            self._do_split_convert(paths, out_dir)
            return

        requests = [
            ConvertRequest(
                p, out_dir, output_format=self.params.format_name,
                quality=self.params.quality, max_size=self.params.max_size,
                sort_by_type=self.params.sort_by_type,
                trim_start=self.preview.get_trim(p)[0],
                trim_end=self.preview.get_trim(p)[1],
                audio_mode=audio_mode,
                audio_format=audio_fmt,
            ) for p in paths
        ]

        self._status_label.setText(_("status_converting"))
        self._progress.setValue(0)
        self._set_busy(True)
        self._btn_convert.setText(_("btn_cancel"))
        self._btn_convert.setStyleSheet(
            f"background-color: {COLORS['error']}; color: white; "
            f"font-weight: bold; padding: 6px 20px;")
        self._disconnect_convert_btn()
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

    def _do_split_convert(self, paths: list[Path], out_dir: Path):
        """Разделение видео+аудио в QThread (без краша GUI)."""
        from conv.core import VIDEO_INPUT

        self._status_label.setText("⏳ Разделение видео+аудио...")
        self._progress.setValue(0)
        self._set_busy(True)

        self._btn_convert.setText(_("btn_cancel"))
        self._btn_convert.setStyleSheet(
            f"background-color: {COLORS['error']}; color: white; "
            f"font-weight: bold; padding: 6px 20px;")
        self._disconnect_convert_btn()

        from PySide6.QtCore import QObject, Signal, Slot

        class SplitWorker(QObject):
            progress = Signal(int, int)
            file_done_signal = Signal(object, object)  # path, result
            finished_signal = Signal(object, bool)  # results, cancelled

            def __init__(self, converter, paths, out_dir, params, trim_map):
                super().__init__()
                self.converter = converter
                self.paths = paths
                self.out_dir = out_dir
                self.params = params
                self.trim_map = trim_map  # {Path: (start, end)} — захвачено до треда
                self._cancel = False

            def cancel(self):
                self._cancel = True

            @Slot()
            def run(self):
                from conv.core import VIDEO_INPUT
                results: list = []
                total = len(self.paths)
                audio_fmt = self.params.audio_split_format
                vfmt = self.params.format_name or 'mp4'
                sort = self.params.sort_by_type

                for i, p in enumerate(self.paths):
                    if self._cancel:
                        break
                    ts, te = self.trim_map.get(p, (0.0, 0.0))
                    if p.suffix.lower() not in VIDEO_INPUT:
                        req = ConvertRequest(p, self.out_dir, output_format=vfmt,
                                             quality=self.params.quality,
                                             max_size=self.params.max_size,
                                             sort_by_type=sort,
                                             trim_start=ts, trim_end=te)
                        res = self.converter.convert_one(req)
                        self.file_done_signal.emit(p, res)
                        results.append(res)
                    else:
                        vp, ap, err = self.converter.split_audio_video(
                            p, self.out_dir, vfmt, audio_fmt,
                            self.params.quality,
                            ts, te,
                            sort_by_type=sort,
                        )
                        res = ConvertResult(
                            request=ConvertRequest(p, self.out_dir),
                            output_path=vp, ok=err is None,
                            error=err or '',
                        )
                        self.file_done_signal.emit(p, res)
                        results.append(res)
                    self.progress.emit(i + 1, total)

                self.finished_signal.emit(results, self._cancel)

        # Захватываем trim ДО старта треда (из главного потока)
        trim_map = {p: self.preview.get_trim(p) for p in paths}

        self._split_worker = SplitWorker(
            self.converter, paths, out_dir, self.params, trim_map,
        )
        self._split_thread = QThread(self)
        self._split_worker.moveToThread(self._split_thread)

        self._split_thread.started.connect(self._split_worker.run)
        self._split_worker.progress.connect(self._on_split_progress)
        self._split_worker.file_done_signal.connect(self._on_split_file_done)
        self._split_worker.finished_signal.connect(self._on_split_finished)
        self._split_worker.finished_signal.connect(self._split_thread.quit)
        self._split_worker.finished_signal.connect(self._split_worker.deleteLater)
        self._split_thread.finished.connect(self._split_thread.deleteLater)

        self._split_thread.start()

    def _on_split_progress(self, done: int, total: int):
        self._progress.setValue(int(done / total * 100))
        self._status_label.setText(f"⏳ Разделение... {done}/{total}")

    def _on_split_file_done(self, path, result):
        self.file_table.set_result(path, result)

    def _on_split_finished(self, results, cancelled: bool):
        ok = sum(1 for r in results if r.ok)
        total = len(results)
        fail = total - ok

        if cancelled and ok == 0:
            self._status_label.setText(_("status_cancelled"))
        elif fail == 0:
            self._status_label.setText(f"✅ Готово: {ok}/{total}")
            self._btn_open.setEnabled(True)
        else:
            self._status_label.setText(f"✅ {ok}/{total}  ❌ {fail}/{total}")
            if ok > 0:
                self._btn_open.setEnabled(True)

        self._progress.setValue(100 if ok > 0 else 0)
        self._btn_convert.setText(_("btn_convert"))
        self._btn_convert.setStyleSheet(
            f"background-color: {COLORS['accent']}; color: {COLORS['bg']}; "
            f"font-weight: bold; padding: 6px 20px;")
        self._disconnect_convert_btn()
        self._btn_convert.clicked.connect(self._do_convert)
        self._set_busy(False)
        self._update_buttons()

        for r in results:
            self.history.add_from_result(r, "Разделение")

        self._split_worker = None
        self._split_thread = None

    def _cancel_convert(self):
        if self._worker:
            self._worker.cancel()
            self._status_label.setText(_("status_cancelling"))
        if hasattr(self, '_split_worker') and self._split_worker:
            self._split_worker.cancel()
            self._status_label.setText(_("status_cancelling"))

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
            f"⏳ {done}/{total}  ({_fmt_time(elapsed)} / ~{_fmt_time(eta)})")

    def _on_file_done(self, result):
        self.file_table.set_result(result.request.input_path, result)

    def _on_finish(self, results, cancelled: bool):
        ok = sum(1 for r in results if r.ok)
        total = len(results)
        fail = total - ok

        if cancelled and ok == 0:
            self._status_label.setText(_("status_cancelled"))
        elif fail == 0:
            self._status_label.setText(f"{_('status_ready')} {ok}/{total}")
            self._btn_open.setEnabled(ok > 0)
        else:
            self._status_label.setText(f"✅ {ok}/{total}  ❌ {fail}/{total}")
            self._btn_open.setEnabled(ok > 0)

        total_src = sum(r.src_size for r in results)
        total_dst = sum(r.dst_size for r in results if r.ok)
        total_time = sum(r.took for r in results)
        if total_src > 0:
            pct = total_dst / total_src * 100 if total_dst > 0 else 0
            self._stats_label.setText(
                f"📦 {fmt_size(total_src)} → {fmt_size(total_dst)} "
                f"({pct:.0f}%)  ⏱ {_fmt_time(total_time)}")

        self._progress.setValue(100 if ok > 0 else 0)
        self._btn_convert.setText(_("btn_convert"))
        self._btn_convert.setStyleSheet(
            f"background-color: {COLORS['accent']}; color: {COLORS['bg']}; "
            f"font-weight: bold; padding: 6px 20px;")
        self._disconnect_convert_btn()
        self._btn_convert.clicked.connect(self._do_convert)
        self._set_busy(False)
        self._update_buttons()

        for r in results:
            self.history.add_from_result(r, "Конвертация")
        self.config.last_output_dir = self._out_dir_edit.text()
        self.config.sort_by_type = self.params.sort_by_type
        self._worker = None
        self._thread = None
        log.info("Конвертация завершена: %d/%d успешно", ok, total)

    def _disconnect_convert_btn(self):
        """Безопасно отключить clicked (не падает, если ничего не подключено)."""
        try:
            self._btn_convert.clicked.disconnect()
        except (TypeError, RuntimeError):
            pass

    # ── About / Язык / Тема ────────────────────────────────────────────

    def _show_about(self):
        dlg = AboutDialog(self)
        dlg.exec()

    def _toggle_language(self):
        new_lang = "en" if self.config.language == "ru" else "ru"
        self.config.language = new_lang
        set_lang(new_lang)
        self._retranslate()
        self._btn_lang.setText("🇬🇧 EN" if new_lang == "ru" else "🇷🇺 RU")
        log.info("Язык: %s", new_lang)

    def _toggle_theme(self):
        themes = ["dark", "light", "system"]
        cur = self.config.theme
        next_idx = (themes.index(cur) + 1) % len(themes) if cur in themes else 0
        new_theme = themes[next_idx]
        self._apply_theme(new_theme)
        self.config.theme = new_theme
        labels = {"dark": "🌙", "light": "☀️", "system": "💻"}
        self._btn_theme.setText(labels[new_theme])
        log.info("Тема: %s", new_theme)

    def _apply_theme(self, name: str):
        app = QApplication.instance()
        if name == "dark":
            apply_dark_theme(app)
        elif name == "light":
            apply_light_theme(app)
        elif name == "system":
            apply_system_theme(app)
        # Обновление стилей для заголовка и кнопки конвертации
        self._header.setStyleSheet(
            f"font-size: 20px; font-weight: bold; color: {COLORS['accent']};")
        self._btn_convert.setStyleSheet(
            f"background-color: {COLORS['accent']}; color: {COLORS['bg']}; "
            f"font-weight: bold; padding: 6px 20px;")

    def _retranslate(self):
        """Обновить тексты всех виджетов при смене языка."""
        self.setWindowTitle(_("window_title"))
        self._header.setText(_("header"))
        self._btn_select.setText(_("btn_select_files"))
        self._btn_select_dir.setText(_("btn_select_folder"))
        self._btn_clear.setText(_("btn_clear"))
        self._btn_select_all.setText(_("btn_select_all"))
        self._btn_select_none.setText(_("btn_deselect_all"))
        self._btn_invert.setText(_("btn_invert"))
        self._btn_tools.setText(_("btn_check_tools"))
        self._btn_logs.setText(_("btn_logs"))
        self._btn_about.setText(_("btn_about"))
        self._out_label.setText(_("output_label"))
        self._btn_convert.setText(_("btn_convert"))
        self._btn_open.setText(_("btn_open_folder"))
        if not self._worker:
            self._status_label.setText(_("status_waiting"))
        # Обновляем таблицу (заголовки)
        self.file_table.retranslate()

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
        lines = ["  ✅  " + label if tools.get(k) else "  ❌  " + label
                 for k, label in labels.items()]
        msg = _("tools_title") + "\n\n" + "\n".join(lines)

        missing = [k for k, v in tools.items() if not v]
        if missing:
            tips = {
                "ffmpeg": "apt install ffmpeg",
                "rsvg_convert": "apt install librsvg2-bin",
                "pil": "pip install Pillow",
                "pillow_heif": "pip install pillow-heif",
            }
            msg += _("tools_missing") + "\n" + "\n".join(
                f"  {k}: {tips.get(k, '?')}" for k in missing)

        QMessageBox.information(self, _("tools_title"), msg)
        log.info("Проверка инструментов: %s", tools)

    def _copy_logs(self):
        lines = log_tail(80)
        QApplication.clipboard().setText(lines)
        orig = self._btn_logs.text()
        self._btn_logs.setText("✅ Скопировано!")
        threading.Timer(2.0, lambda: self._btn_logs.setText(orig)).start()

    def _on_files_removed(self, paths: list[Path]):
        self._update_buttons()
        if self.preview.current_path in paths:
            self.preview.clear()
        if self.file_table.count > 0:
            self._show_preview(0)

    # ── Горячие клавиши ───────────────────────────────────────────────

    def _setup_shortcuts(self):
        def _sc(keys: str):
            s = QShortcut(QKeySequence(keys), self)
            s.setContext(Qt.ApplicationShortcut)
            return s

        _sc("Ctrl+A").activated.connect(lambda: self.file_table.set_all_checked(True))
        _sc("Ctrl+Shift+A").activated.connect(lambda: self.file_table.set_all_checked(False))
        _sc("Ctrl+I").activated.connect(self.file_table.invert_selection)
        _sc("Delete").activated.connect(self._delete_selected)
        _sc("Return").activated.connect(self._do_convert)
        _sc("Ctrl+O").activated.connect(self._select_files)
        _sc("Ctrl+Shift+O").activated.connect(self._select_folder)
        _sc("Ctrl+.").activated.connect(self._open_output)
        _sc("Escape").activated.connect(self._cancel_or_clear)
        _sc("Space").activated.connect(self._toggle_playback)
        log.info("Горячие клавиши: Ctrl+A/Shift+A/I/Delete/Enter/Ctrl+O/Space/Esc")

    def _delete_selected(self):
        path = self.file_table.current_path
        if path is not None:
            self.file_table.remove_files([path])
            self._update_buttons()
            if self.preview.current_path == path:
                self.preview.clear()
            if self.file_table.count > 0:
                self._show_preview(0)

    def _cancel_or_clear(self):
        if self._worker is not None:
            self._cancel_convert()
        elif self.file_table.count > 0:
            self._clear_all()

    def _toggle_playback(self):
        if hasattr(self, "preview"):
            self.preview.toggle_video_playback()

    # ── Конфиг ─────────────────────────────────────────────────────────

    def _apply_config(self):
        if self.config.last_output_dir:
            self._out_dir_edit.setText(self.config.last_output_dir)
        self.params.sort_by_type = self.config.sort_by_type
