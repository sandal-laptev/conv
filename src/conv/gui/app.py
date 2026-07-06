"""Главное окно ConvApp — сборка всех виджетов."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from conv.core import Converter, ConvertRequest
from conv.gui.controllers.conversion import ConversionController
from conv.gui.theme import COLORS, fmt_size, fmt_time
from conv.history import HistoryManager, ConfigManager
from conv.gui.history_window import HistoryWindow
from conv.gui.widgets.drop_zone import DropZone
from conv.gui.widgets.file_list import FileList
from conv.gui.widgets.params import ParamsPanel
from conv.gui.widgets.preview import PreviewPanel
from conv.logger import get_logger, tail as log_tail

log = get_logger("conv.gui")


class ConvApp(ctk.CTk):
    """Главное окно приложения."""

    def __init__(self):
        super().__init__()
        self.title("🖧 conv — Иохим Кузьмич Media Converter")
        self.geometry("1100x720")
        self.minsize(700, 600)

        self.converter = Converter()
        self.history = HistoryManager()
        self.config = ConfigManager()
        self.preview_index = 0

        self._build_ui()
        self._apply_config()
        self._update_preview()

        # Фоновая проверка инструментов
        self.after(100, self._check_tools_background)

        log.info("GUI запущен (CustomTkinter)")

    # ── Сборка UI ─────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)  # content area

        # Header
        ctk.CTkLabel(
            self, text="🖧  conv  —  Иохим Кузьмич Media Converter",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["accent"],
        ).grid(row=0, column=0, pady=(15, 5), padx=15, sticky="w")

        # Drop zone
        self.drop_zone = DropZone(self, on_files_selected=self._on_files_selected)
        self.drop_zone.grid(row=1, column=0, pady=5, padx=15, sticky="ew")

        # Params
        self.params = ParamsPanel(
            self, on_format_changed=self._on_format_changed,
        )
        self.params.grid(row=2, column=0, pady=(5, 0), padx=15, sticky="ew")

        # Output options row
        self._build_output_options()

        # Content: file list + preview
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=4, column=0, pady=5, padx=15, sticky="nsew")
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=3)
        content.grid_columnconfigure(1, weight=2)

        self.file_list = FileList(content, on_file_click=self._on_file_click)
        self.file_list.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        self.preview = PreviewPanel(
            content,
            on_prev=self._preview_prev,
            on_next=self._preview_next,
            on_trim_changed=self._on_trim_changed,
        )
        self.preview.grid(row=0, column=1, sticky="nsew")

        # Buttons
        self._build_buttons()

        # Progress + status
        self._build_status()

        log.debug("UI построен")

    def _build_output_options(self):
        """Строка: выбор выходной папки + чекбокс сортировки по типу."""
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=3, column=0, pady=(2, 0), padx=15, sticky="ew")
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="📁 Выход:", text_color=COLORS["text2"]).grid(
            row=0, column=0, sticky="w")

        self._out_dir_var = ctk.StringVar(value=str(Path.cwd() / "CONVERTED"))
        self._out_dir_entry = ctk.CTkEntry(
            frame, textvariable=self._out_dir_var, width=350,
            fg_color=COLORS["surface"], text_color=COLORS["text"],
        )
        self._out_dir_entry.grid(row=0, column=1, sticky="w", padx=5)

        ctk.CTkButton(
            frame, text="📂", width=30,
            fg_color=COLORS["surface2"], text_color=COLORS["text2"],
            command=self._choose_output_dir,
        ).grid(row=0, column=2, padx=(0, 10))

        self._sort_by_type_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            frame, text="📁 Сортировать по типу (image/video/audio)",
            variable=self._sort_by_type_var,
            text_color=COLORS["text2"],
            command=self._on_sort_by_type_changed,
        ).grid(row=0, column=3, padx=(10, 0))

    def _choose_output_dir(self):
        from tkinter import filedialog
        d = filedialog.askdirectory(
            title="Выберите папку для сохранения",
            initialdir=self._out_dir_var.get(),
        )
        if d:
            self._out_dir_var.set(d)
            self.config.last_output_dir = d

    def _on_sort_by_type_changed(self):
        self.config.sort_by_type = self._sort_by_type_var.get()

    def _apply_config(self):
        """Загрузить сохранённые настройки."""
        if self.config.last_output_dir:
            p = Path(self.config.last_output_dir)
            self._out_dir_var.set(str(p))
        self._sort_by_type_var.set(self.config.sort_by_type)

    def _build_buttons(self):
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=5, column=0, pady=(5, 0), padx=15, sticky="ew")

        self.convert_btn = ctk.CTkButton(
            btn_frame, text="⚡ Конвертировать",
            fg_color=COLORS["accent"], text_color=COLORS["bg"],
            hover_color="#00b8e6",
            command=self._do_convert, state="disabled",
        )
        self.convert_btn.grid(row=0, column=0, padx=(0, 8))

        self.clear_btn = ctk.CTkButton(
            btn_frame, text="🗑 Очистить",
            fg_color=COLORS["surface2"], text_color=COLORS["text2"],
            command=self._clear_all, state="disabled",
        )
        self.clear_btn.grid(row=0, column=1, padx=(0, 8))

        self.open_btn = ctk.CTkButton(
            btn_frame, text="📂 Открыть",
            fg_color=COLORS["surface2"], text_color=COLORS["text2"],
            command=self._open_output, state="disabled",
        )
        self.open_btn.grid(row=0, column=2, padx=(0, 8))

        ctk.CTkButton(
            btn_frame, text="🔧 Проверить",
            fg_color=COLORS["surface2"], text_color=COLORS["text2"],
            command=self._check_tools,
        ).grid(row=0, column=3, padx=(0, 8))

        self.log_btn = ctk.CTkButton(
            btn_frame, text="📋 Логи",
            fg_color=COLORS["surface2"], text_color=COLORS["text2"],
            command=self._copy_logs,
        )
        self.log_btn.grid(row=0, column=4, padx=(0, 8))

        ctk.CTkButton(
            btn_frame, text="📜 История",
            fg_color=COLORS["surface2"], text_color=COLORS["text2"],
            command=self._show_history,
        ).grid(row=0, column=5, padx=(0, 8))

        ctk.CTkButton(
            btn_frame, text="✕ Закрыть",
            fg_color=COLORS["surface2"], text_color=COLORS["text2"],
            command=self.destroy,
        ).grid(row=0, column=6)

    def _build_status(self):
        status_frame = ctk.CTkFrame(self, fg_color="transparent")
        status_frame.grid(row=6, column=0, pady=(5, 15), padx=15, sticky="ew")
        status_frame.grid_columnconfigure(1, weight=1)

        self.progress_bar = ctk.CTkProgressBar(
            status_frame, width=400,
            fg_color=COLORS["surface"], progress_color=COLORS["accent"],
        )
        self.progress_bar.grid(
            row=0, column=0, columnspan=2, pady=(0, 4), sticky="ew",
        )
        self.progress_bar.set(0)

        self.status_var = ctk.StringVar(value="Ожидание файлов...")
        ctk.CTkLabel(
            status_frame, textvariable=self.status_var,
            text_color=COLORS["text2"], anchor="w",
        ).grid(row=1, column=0, sticky="w")

        self.stats_var = ctk.StringVar(value="")
        ctk.CTkLabel(
            status_frame, textvariable=self.stats_var,
            text_color=COLORS["text3"], anchor="e",
        ).grid(row=1, column=1, sticky="e")

    # ── Файлы ─────────────────────────────────────────────────────────

    def _on_files_selected(self, paths: list[Path]):
        self.file_list.add_files(paths)
        self._update_buttons()
        self._update_preview()

    def _clear_all(self):
        self.file_list.clear()
        self.preview.clear()
        self.preview_index = 0
        self.progress_bar.set(0)
        self.status_var.set("Ожидание файлов...")
        self.stats_var.set("")
        self._update_buttons()
        log.info("Список очищен")

    def _update_buttons(self):
        has_files = self.file_list.count > 0
        self.convert_btn.configure(
            state="normal" if has_files and not getattr(
                self, "_controller_running", False,
            ) else "disabled",
        )
        self.clear_btn.configure(
            state="normal" if has_files else "disabled",
        )

    # ── Формат ────────────────────────────────────────────────────────

    def _on_format_changed(self):
        self.file_list.set_format(self.params.format_name)
        self._update_preview()

    # ── Превью ────────────────────────────────────────────────────────

    def _on_file_click(self, idx: int):
        self.preview_index = idx
        self._update_preview()

    def _preview_prev(self):
        if self.file_list.count > 0 and self.preview_index > 0:
            self.preview_index -= 1
            self._update_preview()

    def _preview_next(self):
        if self.file_list.count > 0 and self.preview_index < self.file_list.count - 1:
            self.preview_index += 1
            self._update_preview()

    def _update_preview(self):
        if not self.file_list.paths:
            self.preview.clear()
            return
        if self.preview_index >= self.file_list.count:
            self.preview_index = self.file_list.count - 1

        path = self.file_list.paths[self.preview_index]
        res = self.file_list.results.get(path)

        self.preview.show(
            path=path,
            idx=self.preview_index,
            total=self.file_list.count,
            fmt_var=self.params.format_raw,
            quality=self.params.quality,
            max_size=self.params.max_size,
            result_size=res.dst_size if res and res.ok else 0,
            result_time=res.fmt_took() if res and res.ok else "",
        )

    # ── Конвертация ───────────────────────────────────────────────────

    def _on_trim_changed(self, path: Path):
        """Вызывается при изменении обрезки.
        НЕ вызываем _update_preview() — он запускает ffmpeg/ffprobe
        синхронно и вешает GUI на каждом движении слайдера.
        PreviewPanel сам обновляет маркеры, поля и метку длительности.
        """

    def _do_convert(self):
        if self.file_list.count == 0:
            return

        self.file_list.reset_results()

        # ── Режим переименования (без ffmpeg) ──
        if self.params.rename_only:
            ext = self.params.format_name
            if not ext:
                self.status_var.set("⚠ Выберите формат для переименования")
                return
            self.status_var.set(f"⏳ Переименование в .{ext}...")
            self.progress_bar.set(0)
            results = self.converter.rename_many(
                self.file_list.paths, ext,
                on_progress=lambda d, t, r: self.progress_bar.set(d / t),
            )
            # Переносим результаты в file_list
            for r in results:
                self.file_list._results[r.request.input_path] = r
            self.file_list._rebuild()
            self._update_preview()
            ok = sum(1 for r in results if r.ok)
            fail = len(results) - ok
            if fail == 0:
                status = f"✅ Переименовано: {ok}"
            else:
                status = f"✅ {ok}  ❌ {fail}"
            self.status_var.set(status)
            self.progress_bar.set(1.0)
            self._update_buttons()
            # Сохраняем в историю
            for r in results:
                self.history.add_from_result(r, "Переименование")
            return

        # ── Обычная конвертация ──
        self._controller_running = True

        out_dir = Path(self._out_dir_var.get())
        out_dir.mkdir(parents=True, exist_ok=True)

        requests = [
            ConvertRequest(
                p, out_dir,
                output_format=self.params.format_name,
                quality=self.params.quality,
                max_size=self.params.max_size,
                trim_start=self.preview.get_trim(p)[0],
                trim_end=self.preview.get_trim(p)[1],
                sort_by_type=self._sort_by_type_var.get(),
            )
            for p in self.file_list.paths
        ]

        self.status_var.set("⏳ Конвертация...")
        self.progress_bar.set(0)
        self.convert_btn.configure(
            text="⏹ Отмена", fg_color=COLORS["error"],
            command=self._cancel_convert,
        )
        self.open_btn.configure(state="disabled")
        self._update_buttons()

        self._controller = ConversionController(
            converter=self.converter,
            on_progress=self._on_progress,
            on_finish=self._on_finish,
        )
        self._controller.start(requests)

    def _cancel_convert(self):
        if hasattr(self, "_controller"):
            self._controller.cancel()

    def _on_progress(self, done: int, total: int, elapsed: float, eta: float):
        self.progress_bar.set(done / total)
        self.status_var.set(
            f"⏳ {done}/{total}  ({fmt_time(elapsed)} / ~{fmt_time(eta)})",
        )
        # Не перестраиваем весь список на каждый файл — только результат

    def _on_finish(self, results, cancelled: bool):
        self._controller_running = False

        # Переносим результаты
        for r in results:
            self.file_list._results[r.request.input_path] = r
        self.file_list._rebuild()
        self._update_preview()

        ok = sum(1 for r in results if r.ok)
        total = len(results)
        fail = total - ok

        if cancelled and ok == 0:
            self.status_var.set("⏹ Отменено")
        elif fail == 0:
            self.status_var.set(f"✅ Готово: {ok}/{total}")
            self.open_btn.configure(state="normal")
        else:
            self.status_var.set(f"✅ {ok}/{total}  ❌ {fail}/{total}")
            if ok > 0:
                self.open_btn.configure(state="normal")

        # Статистика
        total_src = sum(r.src_size for r in results)
        total_dst = sum(r.dst_size for r in results if r.ok)
        total_time = sum(r.took for r in results)
        if total_src > 0:
            pct = total_dst / total_src * 100 if total_dst > 0 else 0
            self.stats_var.set(
                f"📦 {fmt_size(total_src)} → {fmt_size(total_dst)} "
                f"({pct:.0f}%)  ⏱ {fmt_time(total_time)}",
            )

        self.progress_bar.set(1.0)
        self.convert_btn.configure(
            text="⚡ Конвертировать", fg_color=COLORS["accent"],
            command=self._do_convert,
        )
        self._update_buttons()
        log.info("Конвертация завершена: %d/%d успешно", ok, total)
        # Сохраняем в историю
        for r in results:
            self.history.add_from_result(r, "Конвертация")
        # Сохраняем настройки
        self.config.last_output_dir = self._out_dir_var.get()
        self.config.sort_by_type = self._sort_by_type_var.get()

    # ── Открыть папку ──

    def _open_output(self):
        out_dir = Path(self._out_dir_var.get())
        if out_dir.exists():
            if os.name == "posix":
                os.system(f'xdg-open "{out_dir}"')
            else:
                os.system(f'start "" "{out_dir}"')

    # ── Проверка инструментов ──

    def _show_history(self):
        """Открыть окно истории."""
        win = HistoryWindow(self, self.history)
        win.focus()

    def _check_tools_background(self):
        tools = self.converter.check_tools()
        missing = [k for k, v in tools.items() if not v]
        if missing:
            names = {
                "ffmpeg": "ffmpeg",
                "rsvg_convert": "rsvg-convert",
                "pil": "Pillow",
                "pillow_heif": "pillow-heif",
            }
            labels = [names.get(k, k) for k in missing]
            self.status_var.set(f"⚠ Не найдены: {', '.join(labels)}")
            log.warning("Отсутствуют инструменты: %s", missing)
        else:
            log.info("Все инструменты доступны")

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

        messagebox.showinfo("🔧 Проверка инструментов", msg)
        log.info("Проверка инструментов: %s", tools)

    # ── Логи ──

    def _copy_logs(self):
        lines = log_tail(80)
        self.clipboard_clear()
        self.clipboard_append(lines)
        orig = self.log_btn.cget("text")
        self.log_btn.configure(text="✅ Скопировано!")
        threading.Timer(
            2.0,
            lambda: self.after(0, lambda: self.log_btn.configure(text=orig)),
        ).start()
        log.info(
            "Логи скопированы в буфер (%d строк)",
            len(lines.split("\n")) - 1,
        )
