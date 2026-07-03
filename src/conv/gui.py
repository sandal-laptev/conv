"""conv GUI — CustomTkinter-интерфейс."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox

from conv.core import (
    Converter,
    ConvertRequest,
    ConvertResult,
    OUTPUT_FORMATS,
    QUALITY_PRESETS,
    VIDEO_INPUT,
    AUDIO_INPUT,
    SVG_INPUT,
    ALL_INPUT,
    resolve_format as resolve_fmt,
)
from conv.logger import get_logger, tail as log_tail, log_path as log_file_path

log = get_logger("conv.gui")

# ── Цветовая схема ───────────────────────────────────────────────────────────

COLORS = {
    "bg": "#0a0a2e",
    "surface": "#1a1a3e",
    "surface2": "#252550",
    "accent": "#00d4ff",
    "accent2": "#7b2ff7",
    "success": "#00e676",
    "error": "#ff1744",
    "text": "#e0e0e0",
    "text2": "#9e9e9e",
    "text3": "#616161",
}

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ── Хелперы ──────────────────────────────────────────────────────────────────

def fmt_size(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.2f} TB"


def fmt_time(s: float) -> str:
    if s < 60:
        return f"{s:.1f}с"
    m, r = divmod(s, 60)
    if m < 60:
        return f"{int(m)}м {r:.0f}с"
    h, m = divmod(m, 60)
    return f"{int(h)}ч {int(m)}м"


# ── Главное окно ─────────────────────────────────────────────────────────────

class ConvApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("🖧 conv — Иохим Кузьмич Media Converter")
        self.geometry("1100x720")
        self.minsize(700, 600)

        # Состояние
        self.converter = Converter()
        self.file_paths: list[Path] = []
        self.file_results: dict[Path, ConvertResult] = {}
        self.is_running = False
        self.cancel_flag = False
        self.preview_index = 0
        self._preview_thumb: ctk.CTkImage | None = None

        self._build_ui()
        self._update_preview()
        log.info("GUI запущен (CustomTkinter)")

    # ── Сборка интерфейса ───────────────────────────────────────────────

    def _build_ui(self):
        # Сетка
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)  # список файлов тянется

        # ── Заголовок ──
        header = ctk.CTkLabel(
            self, text="🖧  conv  —  Иохим Кузьмич Media Converter",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["accent"],
        )
        header.grid(row=0, column=0, pady=(15, 5), padx=15, sticky="w")

        # ── Зона drag'n'drop / выбора файлов ──
        self.drop_frame = ctk.CTkFrame(self, height=100,
                                        fg_color=COLORS["surface"],
                                        border_color=COLORS["accent"],
                                        border_width=2)
        self.drop_frame.grid(row=1, column=0, pady=5, padx=15, sticky="ew")
        self.drop_frame.grid_propagate(False)

        self.drop_label = ctk.CTkLabel(
            self.drop_frame,
            text="📁  Нажмите для выбора файлов  (или перетащите сюда)",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text2"],
        )
        self.drop_label.place(relx=0.5, rely=0.5, anchor="center")

        # drag'n'drop через tkinterdnd2
        try:
            self.drop_frame.drop_target_register(".*")
            self.drop_frame.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            log.warning("DnD не поддерживается на этой платформе")

        self.drop_frame.bind("<Button-1>", self._pick_files)
        self.drop_label.bind("<Button-1>", self._pick_files)

        # ── Параметры ──
        params_frame = ctk.CTkFrame(self, fg_color="transparent")
        params_frame.grid(row=2, column=0, pady=(5, 0), padx=15, sticky="ew")
        params_frame.grid_columnconfigure((0, 1, 2), weight=1)

        # Пресет
        ctk.CTkLabel(params_frame, text="Пресет:", text_color=COLORS["text2"]).grid(
            row=0, column=0, sticky="w")
        preset_options = [f"{v.label} — {v.description}" for v in QUALITY_PRESETS.values()] + ["— Кастом"]
        self.preset_var = ctk.StringVar(value=preset_options[1])  # web по умолчанию
        preset_menu = ctk.CTkOptionMenu(params_frame, variable=self.preset_var,
                                          values=preset_options, width=300)
        preset_menu.grid(row=1, column=0, sticky="w", padx=(0, 10))
        preset_menu.configure(command=self._on_preset_change)

        # Формат
        fmt_options = ["Авто"] + [f"{k} — {v['desc']}" for k, v in OUTPUT_FORMATS.items()]
        self.fmt_var = ctk.StringVar(value="Авто")
        ctk.CTkLabel(params_frame, text="Формат:", text_color=COLORS["text2"]).grid(
            row=0, column=1, sticky="w")
        fmt_menu = ctk.CTkOptionMenu(params_frame, variable=self.fmt_var,
                                       values=fmt_options, width=160,
                                       command=lambda _: self._refresh_file_list())
        fmt_menu.grid(row=1, column=1, sticky="w", padx=(0, 10))

        # Качество
        ctk.CTkLabel(params_frame, text="Качество:", text_color=COLORS["text2"]).grid(
            row=0, column=2, sticky="w")
        self.quality_var = ctk.IntVar(value=80)
        quality_slider = ctk.CTkSlider(params_frame, variable=self.quality_var,
                                        from_=1, to=100, number_of_steps=99, width=160)
        quality_slider.grid(row=1, column=2, sticky="w", padx=(0, 10))
        self.quality_label = ctk.CTkLabel(params_frame, text="80%", width=40,
                                           text_color=COLORS["accent"])
        self.quality_label.grid(row=1, column=2, sticky="e", padx=(0, 10))
        quality_slider.configure(command=self._on_quality_change)

        # Макс. размер (row 2)
        ctk.CTkLabel(params_frame, text="Макс. px (0 = ориг):",
                     text_color=COLORS["text2"]).grid(row=2, column=1, sticky="w")
        self.size_entry = ctk.CTkEntry(params_frame, width=100, placeholder_text="0")
        self.size_entry.grid(row=2, column=2, sticky="w", padx=(0, 10))
        self.size_entry.insert(0, "1920")
        self.size_entry.bind("<KeyRelease>", self._on_size_change)

        # ── Основная область: список файлов + предпросмотр ──
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.grid(row=3, column=0, pady=5, padx=15, sticky="nsew")
        content_frame.grid_rowconfigure(0, weight=1)
        content_frame.grid_columnconfigure(0, weight=3)  # файлы — 3/5
        content_frame.grid_columnconfigure(1, weight=2)  # превью — 2/5

        # Список файлов (слева)
        self.file_textbox = ctk.CTkTextbox(content_frame, font=ctk.CTkFont(size=12),
                                            fg_color=COLORS["surface"],
                                            text_color=COLORS["text"])
        self.file_textbox.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self.file_textbox.configure(state="disabled")
        self.file_textbox.bind("<Button-1>", self._on_file_list_click)

        # Панель предпросмотра (справа)
        self.preview_frame = ctk.CTkFrame(content_frame, fg_color=COLORS["surface"])
        self.preview_frame.grid(row=0, column=1, sticky="nsew")
        self.preview_frame.grid_rowconfigure(1, weight=1)  # изображение тянется
        self.preview_frame.grid_columnconfigure(0, weight=1)

        # Заголовок превью
        preview_header = ctk.CTkLabel(
            self.preview_frame, text="👁 Предпросмотр",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLORS["accent"],
        )
        preview_header.grid(row=0, column=0, pady=(8, 2), padx=8, sticky="w")

        # Область для миниатюры
        self.preview_image_label = ctk.CTkLabel(
            self.preview_frame, text="",
            fg_color=COLORS["surface2"],
            corner_radius=8,
        )
        self.preview_image_label.grid(row=1, column=0, pady=4, padx=8, sticky="nsew")
        self.preview_image_label.bind("<Configure>", self._on_preview_resize)

        # Навигация + инфо
        nav_frame = ctk.CTkFrame(self.preview_frame, fg_color="transparent")
        nav_frame.grid(row=2, column=0, pady=(4, 0), padx=8, sticky="ew")
        nav_frame.grid_columnconfigure(0, weight=0)
        nav_frame.grid_columnconfigure(1, weight=1)
        nav_frame.grid_columnconfigure(2, weight=0)

        self.preview_prev_btn = ctk.CTkButton(
            nav_frame, text="◀", width=30, fg_color=COLORS["surface2"],
            text_color=COLORS["text"], command=self._preview_prev,
        )
        self.preview_prev_btn.grid(row=0, column=0, padx=(0, 4))

        self.preview_name_label = ctk.CTkLabel(
            nav_frame, text="—", text_color=COLORS["accent"],
            font=ctk.CTkFont(size=11),
        )
        self.preview_name_label.grid(row=0, column=1, sticky="w")

        self.preview_next_btn = ctk.CTkButton(
            nav_frame, text="▶", width=30, fg_color=COLORS["surface2"],
            text_color=COLORS["text"], command=self._preview_next,
        )
        self.preview_next_btn.grid(row=0, column=2, padx=(4, 0))

        # Информация о файле
        self.preview_info_label = ctk.CTkLabel(
            self.preview_frame, text="",
            text_color=COLORS["text2"], anchor="w", justify="left",
            font=ctk.CTkFont(size=11),
        )
        self.preview_info_label.grid(row=3, column=0, pady=(4, 8), padx=8, sticky="ew")

        # ── Кнопки ──
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=4, column=0, pady=(5, 0), padx=15, sticky="ew")
        btn_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=0)

        self.convert_btn = ctk.CTkButton(btn_frame, text="⚡ Конвертировать",
                                          fg_color=COLORS["accent"],
                                          text_color=COLORS["bg"],
                                          hover_color="#00b8e6",
                                          command=self._do_convert,
                                          state="disabled")
        self.convert_btn.grid(row=0, column=0, padx=(0, 8))

        self.clear_btn = ctk.CTkButton(btn_frame, text="🗑 Очистить",
                                        fg_color=COLORS["surface2"],
                                        text_color=COLORS["text2"],
                                        command=self._clear_all,
                                        state="disabled")
        self.clear_btn.grid(row=0, column=1, padx=(0, 8))

        self.open_btn = ctk.CTkButton(btn_frame, text="📂 Открыть",
                                       fg_color=COLORS["surface2"],
                                       text_color=COLORS["text2"],
                                       command=self._open_output,
                                       state="disabled")
        self.open_btn.grid(row=0, column=2, padx=(0, 8))

        self.check_btn = ctk.CTkButton(btn_frame, text="🔧 Проверить",
                                        fg_color=COLORS["surface2"],
                                        text_color=COLORS["text2"],
                                        command=self._check_tools)
        self.check_btn.grid(row=0, column=3, padx=(0, 8))

        self.log_btn = ctk.CTkButton(btn_frame, text="📋 Логи",
                                      fg_color=COLORS["surface2"],
                                      text_color=COLORS["text2"],
                                      command=self._copy_logs)
        self.log_btn.grid(row=0, column=4, padx=(0, 8))

        self.clear_btn = ctk.CTkButton(btn_frame, text="✕ Закрыть",
                                        fg_color=COLORS["surface2"],
                                        text_color=COLORS["text2"],
                                        command=self.destroy)
        self.clear_btn.grid(row=0, column=5)

        # ── Прогресс и статус ──
        status_frame = ctk.CTkFrame(self, fg_color="transparent")
        status_frame.grid(row=5, column=0, pady=(5, 15), padx=15, sticky="ew")
        status_frame.grid_columnconfigure(1, weight=1)

        self.progress_bar = ctk.CTkProgressBar(status_frame, width=400,
                                                fg_color=COLORS["surface"],
                                                progress_color=COLORS["accent"])
        self.progress_bar.grid(row=0, column=0, columnspan=2, pady=(0, 4), sticky="ew")
        self.progress_bar.set(0)

        self.status_var = ctk.StringVar(value="Ожидание файлов...")
        self.status_label = ctk.CTkLabel(status_frame, textvariable=self.status_var,
                                          text_color=COLORS["text2"], anchor="w")
        self.status_label.grid(row=1, column=0, sticky="w")

        self.stats_var = ctk.StringVar(value="")
        self.stats_label = ctk.CTkLabel(status_frame, textvariable=self.stats_var,
                                         text_color=COLORS["text3"], anchor="e")
        self.stats_label.grid(row=1, column=1, sticky="e")

        # ── Проверка инструментов при старте ──
        self.after(100, self._check_tools_background)

        log.debug("UI построен")

    # ── Предпросмотр ──────────────────────────────────────────────────

    def _on_file_list_click(self, event):
        """Клик по списку файлов — выбираем файл для превью."""
        if not self.file_paths:
            return
        # Определяем строку по координате Y
        line_height = 18  # приблизительно
        y = int(event.y / line_height) - 1  # -1 за заголовок
        if 0 <= y < len(self.file_paths):
            self.preview_index = y
            self._update_preview()

    def _on_preview_resize(self, event):
        """Перерисовка превью при изменении размера панели."""
        if self._preview_thumb is not None and self.preview_index < len(self.file_paths):
            self._show_preview_image(self.file_paths[self.preview_index])

    def _preview_prev(self):
        if self.file_paths and self.preview_index > 0:
            self.preview_index -= 1
            self._update_preview()

    def _preview_next(self):
        if self.file_paths and self.preview_index < len(self.file_paths) - 1:
            self.preview_index += 1
            self._update_preview()

    def _update_preview(self):
        """Обновляет панель предпросмотра для текущего файла."""
        if not self.file_paths:
            self.preview_image_label.configure(image="", text="Нет файлов")
            self.preview_name_label.configure(text="—")
            self.preview_info_label.configure(text="")
            self._preview_thumb = None
            self.preview_prev_btn.configure(state="disabled")
            self.preview_next_btn.configure(state="disabled")
            return

        # Индекс
        if self.preview_index >= len(self.file_paths):
            self.preview_index = len(self.file_paths) - 1

        idx = self.preview_index
        path = self.file_paths[idx]

        # Навигация
        self.preview_prev_btn.configure(state="normal" if idx > 0 else "disabled")
        self.preview_next_btn.configure(state="normal" if idx < len(self.file_paths) - 1 else "disabled")
        self.preview_name_label.configure(text=f"  {idx + 1}/{len(self.file_paths)}  {path.name}")

        # Превью изображения
        self._show_preview_image(path)

        # Информация
        self._show_preview_info(path)

    def _show_preview_image(self, path: Path):
        """Показывает миниатюру изображения/видео."""
        ext = path.suffix.lower()
        is_image = ext not in VIDEO_INPUT | AUDIO_INPUT

        if not is_image:
            # Для видео/аудио — иконка типа
            sym = "🎬" if ext in VIDEO_INPUT else "🎵"
            label = f"{sym}\n\n{path.suffix.upper()}\n(предпросмотр недоступен)"
            self.preview_image_label.configure(
                image="", text=label,
                text_color=COLORS["text3"],
                font=ctk.CTkFont(size=24),
            )
            self._preview_thumb = None
            return

        try:
            from PIL import Image as PILImage

            img = PILImage.open(path)

            # Достаём размер панели
            pw = self.preview_image_label.winfo_width() or 280
            ph = self.preview_image_label.winfo_height() or 200
            thumb_size = min(pw - 16, ph - 16, 280)
            thumb_size = max(thumb_size, 80)

            # Ресайз с сохранением пропорций
            img.thumbnail((thumb_size, thumb_size), PILImage.LANCZOS)

            # Конвертируем в RGB если нужно
            if img.mode != "RGB":
                img = img.convert("RGB")

            ctk_img = ctk.CTkImage(
                light_image=img, dark_image=img,
                size=(img.width, img.height),
            )
            self._preview_thumb = ctk_img
            self.preview_image_label.configure(
                image=ctk_img, text="",
            )
        except Exception as e:
            log.debug("Ошибка превью: %s", e)
            self.preview_image_label.configure(
                image="", text=f"❌\n{e!s:.40}",
                text_color=COLORS["error"],
                font=ctk.CTkFont(size=14),
            )
            self._preview_thumb = None

    def _show_preview_info(self, path: Path):
        """Показывает информацию о файле."""
        ext = path.suffix.lower()
        src_size = _size(path)
        size_str = fmt_size(src_size)

        # Тип
        if ext in VIDEO_INPUT:
            type_str = f"🎬 Видео  •  {ext.upper()}"
        elif ext in AUDIO_INPUT:
            type_str = f"🎵 Аудио  •  {ext.upper()}"
        elif ext in SVG_INPUT:
            type_str = f"🖼 SVG  •  {ext.upper()}"
        else:
            type_str = f"🖼 Изображение  •  {ext.upper()}"

        # Размер файла
        lines = [type_str, f"📦 {size_str}"]

        # Размеры изображения
        if ext not in VIDEO_INPUT | AUDIO_INPUT:
            try:
                from PIL import Image as PILImage
                with PILImage.open(path) as img:
                    w, h = img.size
                    lines.append(f"📐 {w}×{h}px")
                    if hasattr(img, 'format') and img.format:
                        lines.append(f"🧩 {img.format}")
            except Exception:
                pass

        # Целевой формат
        fmt_raw = self.fmt_var.get()
        fmt_global = "" if fmt_raw == "Авто" else fmt_raw.split(" — ")[0]
        target_fmt = fmt_global if fmt_global else resolve_fmt('', ext)
        quality = self.quality_var.get()
        max_size = self.size_entry.get() or "0"
        lines.append(f"→ .{target_fmt}  (q={quality}, s={max_size})")

        # Результат конвертации (если есть)
        res = self.file_results.get(path)
        if res and res.ok:
            dst_size = fmt_size(res.dst_size)
            ratio = res.dst_size / res.src_size * 100 if res.src_size > 0 else 0
            lines.append(f"✅ {dst_size}  ({ratio:.0f}%)  — {res.fmt_took()}")

        self.preview_info_label.configure(text="\n".join(lines))

    # ── Качество ──

    def _on_quality_change(self, value):
        self.quality_label.configure(text=f"{int(value)}%")
        # Пользователь тронул качество вручную — сбрасываем пресет на кастом
        self._unset_preset()

    def _on_size_change(self, *_):
        # Пользователь изменил размер вручную — сбрасываем пресет
        self._unset_preset()

    def _unset_preset(self):
        """Сбрасывает пресет на 'Кастом', если был выбран именованный."""
        current = self.preset_var.get()
        # Если в тексте есть тире — значит это именованный пресет, а не 'Кастом'
        if current != '— Кастом':
            self.preset_var.set('— Кастом')

    def _on_preset_change(self, choice: str):
        """Выбран пресет — применяем его параметры."""
        for p in QUALITY_PRESETS.values():
            label_prefix = f"{p.label} — "
            if choice.startswith(label_prefix):
                self.quality_var.set(p.quality)
                self.quality_label.configure(text=f"{p.quality}%")
                self.size_entry.delete(0, "end")
                self.size_entry.insert(0, str(p.max_size))
                log.info("Пресет: %s (q=%d, s=%d)", p.label, p.quality, p.max_size)
                return

    # ── Выбор файлов ──

    def _pick_files(self, event=None):
        if self.is_running:
            return
        files = filedialog.askopenfiles(
            title="Выберите медиафайлы",
            multiple=True,
            filetypes=[("Медиафайлы",
                        " ".join(f"*{e}" for e in sorted(ALL_INPUT))),
                       ("Все файлы", "*.*")],
        )
        if files:
            paths = []
            for f in files:
                p = Path(f.name)
                if p.suffix.lower() in ALL_INPUT:
                    paths.append(p)
                    log.debug("Выбран файл: %s", p.name)
            self._add_files(paths)
            log.info("Выбрано файлов: %d", len(paths))

    def _on_drop(self, event):
        if self.is_running:
            return
        raw = event.data.strip()
        paths = []
        for line in raw.split("\r\n") if "\r\n" in raw else raw.split("\n"):
            line = line.strip().strip("{").strip("}")
            if line:
                p = Path(line)
                if p.exists() and p.suffix.lower() in ALL_INPUT:
                    paths.append(p)
        if paths:
            self._add_files(paths)
            log.info("Дропнуто файлов: %d", len(paths))

    # ── Управление списком файлов ──

    def _add_files(self, paths: list[Path]):
        existing = set(self.file_paths)
        for p in paths:
            if p not in existing:
                self.file_paths.append(p)
                existing.add(p)
        self._refresh_file_list()
        self._update_buttons()
        self._update_preview()

    def _remove_file(self, path: Path):
        if self.is_running:
            return
        if path in self.file_paths:
            self.file_paths.remove(path)
            self.file_results.pop(path, None)
        self._refresh_file_list()
        self._update_buttons()

    def _clear_all(self):
        if self.is_running:
            return
        self.file_paths.clear()
        self.file_results.clear()
        self._refresh_file_list()
        self._update_buttons()
        self.status_var.set("Ожидание файлов...")
        self.stats_var.set("")
        self.progress_bar.set(0)
        self.preview_index = 0
        self._update_preview()
        log.info("Список очищен")

    def _refresh_file_list(self):
        self.file_textbox.configure(state="normal")
        self.file_textbox.delete("0.0", "end")

        if not self.file_paths:
            self.file_textbox.insert("0.0", "  (нет файлов — нажмите на область выше для выбора)\n")
        else:
            # Формат из селектора
            fmt_raw = self.fmt_var.get()
            fmt_global = "" if fmt_raw == "Авто" else fmt_raw.split(" — ")[0]

            # Заголовок
            header = f"  {'📄 Файл':<42} {'→ формат':>10} {'Размер':>8} {'Статус':>10} {'Результат':<25}\n"
            header += f"  {'─'*42} {'─'*10} {'─'*8} {'─'*10} {'─'*25}\n"
            self.file_textbox.insert("end", header)

            for p in self.file_paths:
                ext = p.suffix.lower()
                sym = "🎬" if ext in VIDEO_INPUT else "🎵" if ext in AUDIO_INPUT else "🖼"
                name = f"{sym} {p.name}"

                # Целевой формат
                target_fmt = fmt_global if fmt_global else resolve_fmt('', ext)
                fmt_str = f".{target_fmt}"

                size_str = fmt_size(_size(p))

                res = self.file_results.get(p)
                if res and res.ok:
                    status = "✅ OK"
                    info = f"{fmt_size(res.dst_size)} ({res.dst_size / res.src_size * 100:.0f}%) — {res.fmt_took()}" if res.src_size > 0 else "done"
                elif res and not res.ok:
                    status = "❌ ERR"
                    info = res.error[:40]
                else:
                    status = "⏳"
                    info = ""

                line = f"  {name:<40} {fmt_str:>10} {size_str:>8} {status:>10} {info:<25}\n"
                self.file_textbox.insert("end", line)

        self.file_textbox.configure(state="disabled")

    def _update_buttons(self):
        has_files = len(self.file_paths) > 0
        self.convert_btn.configure(state="normal" if has_files and not self.is_running else "disabled")
        self.clear_btn.configure(state="normal" if has_files and not self.is_running else "disabled")

    # ── Конвертация ──

    def _do_convert(self):
        if self.is_running or not self.file_paths:
            return

        self.is_running = True
        self.cancel_flag = False
        self.file_results.clear()

        # Парсим формат
        fmt_raw = self.fmt_var.get()
        fmt = ""
        if fmt_raw != "Авто":
            fmt = fmt_raw.split(" — ")[0]

        quality = self.quality_var.get()
        max_size = int(self.size_entry.get() or "0")

        out_dir = Path.cwd() / "CONVERTED"
        out_dir.mkdir(exist_ok=True, parents=True)

        requests = [
            ConvertRequest(p, out_dir, output_format=fmt,
                           quality=quality, max_size=max_size)
            for p in self.file_paths
        ]

        total = len(requests)
        done = 0
        start = time.time()

        self.status_var.set("⏳ Конвертация...")
        self.progress_bar.set(0)
        self.convert_btn.configure(text="⏹ Отмена", fg_color=COLORS["error"],
                                   command=self._cancel_convert)
        self.open_btn.configure(state="disabled")
        self._update_buttons()
        self._refresh_file_list()

        def run():
            nonlocal done
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                for req in requests:
                    if self.cancel_flag:
                        break
                    res = self.converter.convert_one(req)
                    self.file_results[req.input_path] = res
                    done += 1

                    elapsed = time.time() - start
                    eta = (elapsed / done * (total - done)) if done > 0 else 0
                    self._ui_thread(lambda: self._update_progress(done, total, elapsed, eta))
                loop.close()
            except Exception as ex:
                log.exception("Ошибка в потоке конвертации")
                self._ui_thread(lambda: self.status_var.set(f"❌ {ex}"))
            finally:
                self.is_running = False
                self._ui_thread(self._finish_convert)

        threading.Thread(target=run, daemon=True).start()
        log.info("Конвертация запущена: %d файлов", total)

    def _cancel_convert(self):
        self.cancel_flag = True
        log.info("Конвертация отменена пользователем")

    def _update_progress(self, done, total, elapsed, eta):
        self.progress_bar.set(done / total)
        self.status_var.set(f"⏳ {done}/{total}  ({fmt_time(elapsed)} / ~{fmt_time(eta)})")
        self._refresh_file_list()

    def _finish_convert(self):
        ok = sum(1 for p in self.file_paths if self.file_results.get(p) and self.file_results[p].ok)
        total = len(self.file_paths)
        fail = total - ok

        if self.cancel_flag and ok == 0:
            self.status_var.set("⏹ Отменено")
        elif fail == 0:
            self.status_var.set(f"✅ Готово: {ok}/{total}")
            self.open_btn.configure(state="normal")
        else:
            self.status_var.set(f"✅ {ok}/{total}  ❌ {fail}/{total}")
            if ok > 0:
                self.open_btn.configure(state="normal")

        total_src = sum(self.file_results[p].src_size for p in self.file_paths if self.file_results.get(p))
        total_dst = sum(self.file_results[p].dst_size for p in self.file_paths
                        if self.file_results.get(p) and self.file_results[p].ok)
        total_time = sum(self.file_results[p].took for p in self.file_paths if self.file_results.get(p))
        if total_src > 0:
            pct = total_dst / total_src * 100 if total_dst > 0 else 0
            self.stats_var.set(f"📦 {fmt_size(total_src)} → {fmt_size(total_dst)} ({pct:.0f}%)  ⏱ {fmt_time(total_time)}")

        self.progress_bar.set(1.0)
        self.convert_btn.configure(text="⚡ Конвертировать", fg_color=COLORS["accent"],
                                   command=self._do_convert)
        self._update_buttons()
        self._refresh_file_list()
        log.info("Конвертация завершена: %d/%d успешно", ok, total)

    def _ui_thread(self, func):
        """Запускает функцию в главном потоке (thread-safe update)."""
        self.after(0, func)

    # ── Открыть папку ──

    def _open_output(self):
        out_dir = Path.cwd() / "CONVERTED"
        if out_dir.exists():
            if os.name == "posix":
                os.system(f'xdg-open "{out_dir}"')
            else:
                os.system(f'start "" "{out_dir}"')

    # ── Копировать логи ──

    # ── Проверка инструментов ──

    def _check_tools_background(self):
        """Проверка при старте — без модального окна."""
        tools = self.converter.check_tools()
        missing = [k for k, v in tools.items() if not v]
        if missing:
            names = {'ffmpeg': 'ffmpeg', 'rsvg_convert': 'rsvg-convert',
                     'pil': 'Pillow', 'pillow_heif': 'pillow-heif'}
            labels = [names.get(k, k) for k in missing]
            self.status_var.set(f"⚠ Не найдены: {', '.join(labels)}")
            log.warning("Отсутствуют инструменты: %s", missing)
        else:
            log.info("Все инструменты доступны")

    def _check_tools(self):
        """Проверка по кнопке — показывает messagebox."""
        tools = self.converter.check_tools()
        labels = {
            'ffmpeg': 'ffmpeg (видео/аудио)',
            'rsvg_convert': 'rsvg-convert (SVG)',
            'pil': 'Pillow (изображения)',
            'pillow_heif': 'pillow-heif (HEIC/HEIF)',
        }
        lines = []
        for key, label in labels.items():
            ok = tools.get(key, False)
            sym = "✅" if ok else "❌"
            lines.append(f"  {sym}  {label}")

        msg = "Доступные инструменты:\n\n" + "\n".join(lines)

        missing = [k for k, v in tools.items() if not v]
        if missing:
            tips = {
                'ffmpeg': 'apt install ffmpeg',
                'rsvg_convert': 'apt install librsvg2-bin',
                'pil': 'pip install Pillow',
                'pillow_heif': 'pip install pillow-heif',
            }
            msg += "\n\n⚠ Отсутствуют:\n"
            for k in missing:
                msg += f"\n  {k}: {tips.get(k, '?')}"

        messagebox.showinfo("🔧 Проверка инструментов", msg)
        log.info("Проверка инструментов: %s", tools)

    def _copy_logs(self):
        lines = log_tail(80)
        self.clipboard_clear()
        self.clipboard_append(lines)
        # Обратная связь
        orig = self.log_btn.cget("text")
        self.log_btn.configure(text="✅ Скопировано!")
        threading.Timer(2.0, lambda: self.after(0, lambda: self.log_btn.configure(text=orig))).start()
        log.info("Логи скопированы в буфер (%d строк)", len(lines.split("\n")) - 1)


def _size(p: Path) -> int:
    try:
        return p.stat().st_size
    except OSError:
        return 0


# ── Точка входа ──────────────────────────────────────────────────────────────

def main_flet():
    """Заглушка для совместимости со старыми entry points."""
    run_gui()


def run_gui():
    app = ConvApp()
    app.mainloop()


if __name__ == "__main__":
    run_gui()
