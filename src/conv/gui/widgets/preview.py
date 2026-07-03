"""Панель предпросмотра: миниатюра, навигация, информация о файле."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import customtkinter as ctk

from conv.core import (
    AUDIO_INPUT,
    SVG_INPUT,
    VIDEO_INPUT,
    MediaInfo,
    get_media_info,
    resolve_format as resolve_fmt,
)
from conv.gui.theme import COLORS, file_size, fmt_size
from conv.logger import get_logger

log = get_logger("conv.preview")

try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    PILImage = None


class PreviewPanel(ctk.CTkFrame):
    """Миниатюра + навигация + информация о выбранном файле.

    Сигналы:
      on_prev_clicked()
      on_next_clicked()
    """

    def __init__(
        self,
        parent,
        on_prev: Callable | None = None,
        on_next: Callable | None = None,
        **kwargs,
    ):
        super().__init__(parent, fg_color=COLORS["surface"], **kwargs)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._on_prev = on_prev
        self._on_next = on_next
        self._thumb: ctk.CTkImage | None = None
        self._has_file = False

        # Заголовок
        ctk.CTkLabel(
            self, text="👁 Предпросмотр",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLORS["accent"],
        ).grid(row=0, column=0, pady=(8, 2), padx=8, sticky="w")

        # Область для миниатюры
        self._image_label = ctk.CTkLabel(
            self, text="",
            fg_color=COLORS["surface2"], corner_radius=8,
        )
        self._image_label.grid(row=1, column=0, pady=4, padx=8, sticky="nsew")
        self._image_label.bind("<Configure>", self._on_resize)

        # Навигация
        nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        nav_frame.grid(row=2, column=0, pady=(4, 0), padx=8, sticky="ew")
        nav_frame.grid_columnconfigure(0, weight=0)
        nav_frame.grid_columnconfigure(1, weight=1)
        nav_frame.grid_columnconfigure(2, weight=0)

        self._prev_btn = ctk.CTkButton(
            nav_frame, text="◀", width=30,
            fg_color=COLORS["surface2"], text_color=COLORS["text"],
            command=self._on_prev_clicked,
        )
        self._prev_btn.grid(row=0, column=0, padx=(0, 4))

        self._name_label = ctk.CTkLabel(
            nav_frame, text="—", text_color=COLORS["accent"],
            font=ctk.CTkFont(size=11),
        )
        self._name_label.grid(row=0, column=1, sticky="w")

        self._next_btn = ctk.CTkButton(
            nav_frame, text="▶", width=30,
            fg_color=COLORS["surface2"], text_color=COLORS["text"],
            command=self._on_next_clicked,
        )
        self._next_btn.grid(row=0, column=2, padx=(4, 0))

        # Информация
        self._info_label = ctk.CTkLabel(
            self, text="",
            text_color=COLORS["text2"], anchor="w", justify="left",
            font=ctk.CTkFont(size=11),
        )
        self._info_label.grid(row=3, column=0, pady=(4, 8), padx=8, sticky="ew")

    # ── Публичное API ──────────────────────────────────────────────────

    def show(self, path: Path | None, idx: int, total: int,
             fmt_var: str, quality: int, max_size: int,
             result_size: int = 0, result_time: str = ""):
        """Обновить превью для указанного файла."""
        if path is None:
            self._image_label.configure(image="", text="Нет файлов")
            self._name_label.configure(text="—")
            self._info_label.configure(text="")
            self._prev_btn.configure(state="disabled")
            self._next_btn.configure(state="disabled")
            self._has_file = False
            return

        self._has_file = True
        self._prev_btn.configure(state="normal" if idx > 0 else "disabled")
        self._next_btn.configure(
            state="normal" if idx < total - 1 else "disabled",
        )
        self._name_label.configure(text=f"  {idx + 1}/{total}  {path.name}")

        self._show_image(path)
        self._show_info(path, fmt_var, quality, max_size, result_size, result_time)

    def clear(self):
        """Сбросить превью."""
        self.show(None, 0, 0, "", 0, 0)

    # ── Миниатюра ──────────────────────────────────────────────────────

    def _show_image(self, path: Path):
        ext = path.suffix.lower()
        is_image = ext not in VIDEO_INPUT | AUDIO_INPUT

        if not is_image:
            sym = "🎬" if ext in VIDEO_INPUT else "🎵"
            # Показываем информацию с иконкой в центре
            info = get_media_info(path)
            lines = [f"{sym}", ext.upper()]
            if info.duration:
                lines.append(info.fmt_duration())
            if info.resolution_str:
                lines.append(info.resolution_str)
            if info.video_codec:
                lines.append(info.video_codec)
            if info.audio_codec:
                lines.append(f"{info.audio_codec}  {info.audio_channels}ch")
            self._image_label.configure(
                image="",
                text="\n".join(lines),
                text_color=COLORS["text3"],
                font=ctk.CTkFont(size=20),
            )
            self._thumb = None
            return

        if not HAS_PIL or PILImage is None:
            self._image_label.configure(
                image="", text="🖼\n(PIL не установлен)",
                text_color=COLORS["text3"], font=ctk.CTkFont(size=18),
            )
            return

        try:
            img = PILImage.open(path)
            pw = self._image_label.winfo_width() or 280
            ph = self._image_label.winfo_height() or 200
            ts = max(min(pw - 16, ph - 16, 280), 80)
            img.thumbnail((ts, ts), PILImage.LANCZOS)
            if img.mode != "RGB":
                img = img.convert("RGB")

            ctk_img = ctk.CTkImage(
                light_image=img, dark_image=img,
                size=(img.width, img.height),
            )
            self._thumb = ctk_img
            self._image_label.configure(image=ctk_img, text="")
        except Exception as e:
            log.debug("Ошибка превью: %s", e)
            self._image_label.configure(
                image="", text=f"❌\n{e!s:.40}",
                text_color=COLORS["error"], font=ctk.CTkFont(size=14),
            )
            self._thumb = None

    def _on_resize(self, event):
        if self._thumb is not None and self._has_file:
            ref = self._image_label.cget("image")
            if ref:
                # CTkImage уже закеширован — просто триггер перерисовки
                self._image_label.configure(image=ref)

    # ── Информация ─────────────────────────────────────────────────────

    def _show_info(
        self, path: Path, fmt_var: str, quality: int,
        max_size: int, result_size: int, result_time: str,
    ):
        ext = path.suffix.lower()
        src_size = file_size(path)
        lines = []

        # Тип
        if ext in VIDEO_INPUT:
            lines.append(f"🎬 Видео  •  {ext.upper()}")
        elif ext in AUDIO_INPUT:
            lines.append(f"🎵 Аудио  •  {ext.upper()}")
        elif ext in SVG_INPUT:
            lines.append(f"🖼 SVG  •  {ext.upper()}")
        else:
            lines.append(f"🖼 Изображение  •  {ext.upper()}")

        lines.append(f"📦 {fmt_size(src_size)}")

        if ext in VIDEO_INPUT | AUDIO_INPUT:
            # Медиа-инфо через ffprobe
            info = get_media_info(path)
            if info.duration:
                lines.append(f"⏱ {info.fmt_duration()}")
            if info.bit_rate:
                lines.append(f"📊 {info.fmt_bitrate()}")
            if info.has_video:
                parts = [f"🎞 {info.video_codec}"]
                if info.resolution_str:
                    parts.append(info.resolution_str)
                if info.fps:
                    parts.append(f"{info.fps:.0f}fps")
                lines.append("  ".join(parts))
            if info.has_audio:
                parts = [f"🎵 {info.audio_codec}"]
                ch_map = {'1': 'моно', '2': 'стерео', '6': '5.1', '8': '7.1'}
                parts.append(ch_map.get(str(info.audio_channels), f'{info.audio_channels}ch'))
                if info.sample_rate:
                    parts.append(f"{info.sample_rate // 1000}kHz")
                lines.append("  ".join(parts))
        elif HAS_PIL and PILImage:
            # Размеры изображения
            try:
                with PILImage.open(path) as img:
                    lines.append(f"📐 {img.width}\u00d7{img.height}px")
                    if img.format:
                        lines.append(f"🧩 {img.format}")
            except Exception:
                pass

        # Целевой формат
        fmt_global = "" if fmt_var == "Авто" else fmt_var.split(" — ")[0]
        target = fmt_global or resolve_fmt("", ext)
        lines.append(f"→ .{target}  (q={quality}, s={max_size})")

        # Результат
        if result_size > 0:
            ratio = result_size / src_size * 100 if src_size > 0 else 0
            lines.append(f"✅ {fmt_size(result_size)}  ({ratio:.0f}%)  — {result_time}")

        self._info_label.configure(text="\n".join(lines))

    # ── Навигация ──

    def _on_prev_clicked(self):
        if self._on_prev:
            self._on_prev()

    def _on_next_clicked(self):
        if self._on_next:
            self._on_next()
