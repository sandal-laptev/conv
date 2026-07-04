"""Панель предпросмотра: миниатюра, навигация, информация о файле."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
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
from conv.core import Converter as _Converter
from conv.gui.theme import COLORS, file_size, fmt_size, parse_time, fmt_trim
from conv.gui.widgets.timeline import Timeline, COLOR_IN, COLOR_OUT
from conv.logger import get_logger

log = get_logger("conv.preview")

try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    PILImage = None

# Регистрируем pillow-heif если есть (чтобы HEIC/HEIF превью работали)
if HAS_PIL:
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        pass


class PreviewPanel(ctk.CTkFrame):
    """Миниатюра + навигация + информация о выбранном файле.

    Сигналы:
      on_prev_clicked()
      on_next_clicked()
      on_trim_changed(path)  — когда пользователь меняет обрезку
    """

    def __init__(
        self,
        parent,
        on_prev: Callable | None = None,
        on_next: Callable | None = None,
        on_trim_changed: Callable | None = None,
        **kwargs,
    ):
        super().__init__(parent, fg_color=COLORS["surface"], **kwargs)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._on_prev = on_prev
        self._on_next = on_next
        self._on_trim_changed = on_trim_changed
        self._thumb: ctk.CTkImage | None = None
        self._thumb_file: Path | None = None  # временный файл кадра видео
        self._has_file = False
        self._current_path: Path | None = None
        self._media_duration: float = 0.0
        self._trim_values: dict[Path, tuple[float, float]] = {}
        self._thumb_dir = Path(tempfile.mkdtemp(prefix="conv_thumbs_"))
        self._last_show_params: dict = {}
        self.bind("<Destroy>", self._cleanup_thumbs)

        # Строки сетки: 0-header, 1-thumb, 2-nav, 3-info, 4-trim-header, 5-trim
        # Навигация и инфо подстраиваются вниз

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

        # Информация о файле
        self._info_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._info_frame.grid(row=3, column=0, pady=(4, 2), padx=8, sticky="ew")
        self._info_frame.grid_columnconfigure(0, weight=1)

        self._info_label = ctk.CTkLabel(
            self._info_frame, text="",
            text_color=COLORS["text2"], anchor="w", justify="left",
            font=ctk.CTkFont(size=11),
        )
        self._info_label.grid(row=0, column=0, sticky="ew")

        # ✂ Timeline — визуализация waveform + маркеры (read-only)
        self._timeline = Timeline(self)
        self._timeline.grid(row=4, column=0, pady=(6, 2), padx=8, sticky="ew")

        # Фейдеры (слайдеры) — основное управление обрезкой
        self._slider_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._slider_frame.grid(row=5, column=0, pady=(0, 0), padx=8, sticky="ew")
        self._slider_frame.grid_columnconfigure(1, weight=1)
        self._slider_frame.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(
            self._slider_frame, text="◀",
            font=ctk.CTkFont(size=10), text_color=COLOR_IN,
        ).grid(row=0, column=0, padx=(0, 2), pady=1)

        self._start_slider = ctk.CTkSlider(
            self._slider_frame, from_=0, to=100,
            height=14, button_color=COLOR_IN,
            button_hover_color="#00c853",
            fg_color=COLORS["surface"], progress_color=COLORS["surface2"],
            command=self._on_slider_start,
        )
        self._start_slider.grid(row=0, column=1, padx=2, pady=1, sticky="ew")
        self._start_slider.set(0)

        ctk.CTkLabel(
            self._slider_frame, text="▶",
            font=ctk.CTkFont(size=10), text_color=COLOR_OUT,
        ).grid(row=0, column=2, padx=(8, 2), pady=1)

        self._end_slider = ctk.CTkSlider(
            self._slider_frame, from_=0, to=100,
            height=14, button_color=COLOR_OUT,
            button_hover_color="#d50000",
            fg_color=COLORS["surface"], progress_color=COLORS["surface2"],
            command=self._on_slider_end,
        )
        self._end_slider.grid(row=0, column=3, padx=2, pady=1, sticky="ew")
        self._end_slider.set(100)

        # Панель точного ввода + метка длительности
        self._trim_bar = ctk.CTkFrame(self, fg_color="transparent")
        self._trim_bar.grid(row=6, column=0, pady=(0, 6), padx=8, sticky="ew")
        self._trim_bar.grid_columnconfigure(0, weight=0)
        self._trim_bar.grid_columnconfigure(1, weight=0)
        self._trim_bar.grid_columnconfigure(2, weight=0)
        self._trim_bar.grid_columnconfigure(3, weight=0)
        self._trim_bar.grid_columnconfigure(4, weight=1)

        ctk.CTkLabel(
            self._trim_bar, text="От:",
            font=ctk.CTkFont(size=10), text_color=COLORS["text3"],
        ).grid(row=0, column=0, padx=(6, 2), pady=2)

        self._start_var = ctk.StringVar(value="")
        self._start_entry = ctk.CTkEntry(
            self._trim_bar, textvariable=self._start_var,
            width=55, font=ctk.CTkFont(size=10),
            fg_color=COLORS["surface"], border_color=COLORS["surface2"],
        )
        self._start_entry.grid(row=0, column=1, padx=2, pady=2)
        self._start_entry.bind("<FocusOut>", self._on_entry_trim)
        self._start_entry.bind("<Return>", self._on_entry_trim)

        ctk.CTkLabel(
            self._trim_bar, text="До:",
            font=ctk.CTkFont(size=10), text_color=COLORS["text3"],
        ).grid(row=0, column=2, padx=(8, 2), pady=2)

        self._end_var = ctk.StringVar(value="")
        self._end_entry = ctk.CTkEntry(
            self._trim_bar, textvariable=self._end_var,
            width=55, font=ctk.CTkFont(size=10),
            fg_color=COLORS["surface"], border_color=COLORS["surface2"],
        )
        self._end_entry.grid(row=0, column=3, padx=2, pady=2)
        self._end_entry.bind("<FocusOut>", self._on_entry_trim)
        self._end_entry.bind("<Return>", self._on_entry_trim)

        self._trim_dur_label = ctk.CTkLabel(
            self._trim_bar, text="",
            font=ctk.CTkFont(size=10), text_color=COLORS["text3"],
        )
        self._trim_dur_label.grid(row=0, column=4, padx=(8, 6), pady=2, sticky="e")

        # Скрываем весь блок обрезки по умолчанию
        self._hide_trim()

    # ── Публичное API ──────────────────────────────────────────────────

    def show(self, path: Path | None, idx: int, total: int,
             fmt_var: str, quality: int, max_size: int,
             result_size: int = 0, result_time: str = ""):
        """Обновить превью для указанного файла."""
        self._last_show_params = dict(
            fmt_var=fmt_var, quality=quality, max_size=max_size,
            result_size=result_size, result_time=result_time,
        )
        self._cleanup_thumb_file()
        self._current_path = path

        if path is None:
            self._image_label.configure(image="", text="Нет файлов")
            self._name_label.configure(text="—")
            self._info_label.configure(text="")
            self._prev_btn.configure(state="disabled")
            self._next_btn.configure(state="disabled")
            self._has_file = False
            self._hide_trim()
            return

        self._has_file = True
        self._prev_btn.configure(state="normal" if idx > 0 else "disabled")
        self._next_btn.configure(
            state="normal" if idx < total - 1 else "disabled",
        )
        self._name_label.configure(text=f"  {idx + 1}/{total}  {path.name}")

        # Медиа-длительность для обрезки
        ext = path.suffix.lower()
        if ext in VIDEO_INPUT | AUDIO_INPUT:
            info = get_media_info(path)
            self._media_duration = info.duration
            self._show_trim()
            # Timeline + фейдеры + точный ввод
            ts, te = self._trim_values.get(path, (0.0, 0.0))
            self._timeline.set_file(path)
            self._update_sliders(ts, te)
            self._timeline.set_trim(ts, te)
            self._start_var.set(fmt_trim(ts) if ts > 0 else "")
            self._end_var.set(fmt_trim(te) if te > 0 else "")
            self._update_trim_display()
        else:
            self._media_duration = 0.0
            self._hide_trim()

        self._show_image(path)
        self._show_info(path, fmt_var, quality, max_size, result_size, result_time)

    def clear(self):
        """Сбросить превью."""
        self._cleanup_thumb_file()
        self._current_path = None
        self._media_duration = 0.0
        self.show(None, 0, 0, "", 0, 0)

    def get_trim(self, path: Path) -> tuple[float, float]:
        """Возвращает trim_start и trim_end для указанного файла."""
        return self._trim_values.get(path, (0.0, 0.0))

    def clear_trim(self, path: Path):
        """Сбрасывает обрезку для файла."""
        self._trim_values.pop(path, None)
        if path == self._current_path:
            self._update_sliders(0.0, 0.0)
            self._timeline.set_trim(0.0, 0.0)
            self._start_var.set("")
            self._end_var.set("")
            self._update_trim_display()

    # ── Обрезка ────────────────────────────────────────────────────────

    def _hide_trim(self):
        self._timeline.grid_remove()
        self._slider_frame.grid_remove()
        self._trim_bar.grid_remove()

    def _show_trim(self):
        self._timeline.grid()
        self._slider_frame.grid()
        self._trim_bar.grid()

    def _update_sliders(self, start_sec: float, end_sec: float):
        """Установить позиции слайдеров (в секундах)."""
        dur = max(self._media_duration, 1)
        self._start_slider.configure(to=dur)
        self._end_slider.configure(to=dur)
        self._start_slider.set(max(0, min(start_sec, dur)))
        self._end_slider.set(max(0, min(end_sec or dur, dur)))

    def _apply_trim(self, ts: float, te: float):
        """Применить trim-значения: сохранить, обновить UI, коллбэк.
        Внимание: НЕ вызываем show()/get_media_info/_extract_video_thumb —
        они синхронные и вешают GUI. Обновляем только легковесные элементы.
        """
        if not self._current_path:
            return
        self._trim_values[self._current_path] = (ts, te)
        self._start_var.set(fmt_trim(ts) if ts > 0 else "")
        self._end_var.set(fmt_trim(te) if te > 0 else "")
        self._timeline.set_trim(ts, te)
        self._update_trim_display()
        # Обновляем инфо-текст (без ffmpeg/ffprobe)
        self._refresh_info()
        if self._on_trim_changed:
            self._on_trim_changed(self._current_path)

    def _on_slider_start(self, val: float):
        """Слайдер начала изменился."""
        if not self._current_path or self._media_duration <= 0:
            return
        ts = val
        _, te = self._trim_values.get(self._current_path, (0.0, self._media_duration))
        if te <= 0:
            te = self._media_duration
        if ts >= te:
            ts = max(0, te - 1)
        self._apply_trim(ts, te)

    def _on_slider_end(self, val: float):
        """Слайдер конца изменился."""
        if not self._current_path or self._media_duration <= 0:
            return
        te = val
        ts, _ = self._trim_values.get(self._current_path, (0.0, 0.0))
        if te <= ts:
            te = min(self._media_duration, ts + 1)
        self._apply_trim(ts, te)

    def _on_entry_trim(self, _event=None):
        """Вызывается при вводе в текстовые поля."""
        if not self._current_path:
            return
        ts = parse_time(self._start_var.get())
        te = parse_time(self._end_var.get())
        dur = self._media_duration
        if dur > 0:
            ts = max(0, min(ts, dur - 1 if dur > 0 else 0))
            te = max(ts + 1 if ts > 0 and te <= ts else 0, min(te, dur))
        self._update_sliders(ts, te)
        self._apply_trim(ts, te)

    def _update_trim_display(self):
        """Обновляет метку с длительностью."""
        if not self._current_path or self._media_duration <= 0:
            self._trim_dur_label.configure(text="")
            return
        ts, te = self._trim_values.get(self._current_path, (0.0, 0.0))
        trimmed = (te or self._media_duration) - ts
        trimmed = max(trimmed, 0)
        if ts > 0 or te > 0:
            self._trim_dur_label.configure(
                text=f"✂ {fmt_trim(trimmed)} / {fmt_trim(self._media_duration)}",
                text_color=COLORS["accent"],
            )
        else:
            self._trim_dur_label.configure(
                text=f"⏱ {fmt_trim(self._media_duration)}",
                text_color=COLORS["text3"],
            )

    # ── Миниатюра ──────────────────────────────────────────────────────

    def _show_image(self, path: Path):
        ext = path.suffix.lower()
        is_image = ext not in VIDEO_INPUT | AUDIO_INPUT

        if not is_image:
            if ext in VIDEO_INPUT:
                thumb = self._extract_video_thumb(path)
                if thumb is not None and HAS_PIL:
                    self._display_pil_thumb(thumb)
                    return

            sym = "🎬" if ext in VIDEO_INPUT else "🎵"
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
            self._display_pil_thumb(path)
        except Exception as e:
            log.debug("Ошибка превью: %s", e)
            self._image_label.configure(
                image="", text=f"❌\n{e!s:.40}",
                text_color=COLORS["error"], font=ctk.CTkFont(size=14),
            )
            self._thumb = None

    def _display_pil_thumb(self, img_path: Path):
        img = PILImage.open(img_path)
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

    def _extract_video_thumb(self, path: Path) -> Path | None:
        """Извлекает кадр из центра обрезанного диапазона (или 1с если нет trim)."""
        ffmpeg = _Converter._tool_path("ffmpeg")
        if not ffmpeg:
            return None

        # Центр обрезки
        ts, te = self._trim_values.get(path, (0.0, 0.0))
        info = get_media_info(path)
        dur = info.duration or 30
        start = ts if ts > 0 else 1
        end = te if te > 0 else dur
        if start >= end:
            start = 1
            end = max(dur, 2)
        center = (start + end) / 2

        out = self._thumb_dir / f"{path.stem}_{int(time.time() * 1000)}.jpg"
        try:
            r = subprocess.run(
                [ffmpeg, "-ss", str(center), "-i", str(path),
                 "-vframes", "1", "-q:v", "5", "-y", str(out)],
                capture_output=True, text=True, timeout=30,
            )
            if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
                self._thumb_file = out
                return out
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
            log.debug("Не удалось извлечь кадр: %s", e)

        if out.exists():
            try:
                out.unlink()
            except OSError:
                pass
        return None

    def _cleanup_thumb_file(self):
        if self._thumb_file is not None:
            try:
                if self._thumb_file.exists():
                    self._thumb_file.unlink()
            except OSError:
                pass
            self._thumb_file = None

    def _cleanup_thumbs(self, event=None):
        try:
            shutil.rmtree(self._thumb_dir, ignore_errors=True)
        except Exception:
            pass

    def _on_resize(self, event):
        if self._thumb is not None and self._has_file:
            ref = self._image_label.cget("image")
            if ref:
                self._image_label.configure(image=ref)

    # ── Информация ─────────────────────────────────────────────────────

    def _show_info(
        self, path: Path, fmt_var: str, quality: int,
        max_size: int, result_size: int, result_time: str,
    ):
        ext = path.suffix.lower()
        src_size = file_size(path)
        lines = []

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
            info = get_media_info(path)
            if info.duration:
                dur_str = info.fmt_duration()
                # Показываем обрезанную длительность если есть
                ts, te = self._trim_values.get(path, (0.0, 0.0))
                if ts > 0 or te > 0:
                    trimmed = (te or info.duration) - ts
                    trimmed = max(trimmed, 0)
                    dur_str = f"{fmt_trim(trimmed)} ✂ ({dur_str})"
                lines.append(f"⏱ {dur_str}")
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
            try:
                with PILImage.open(path) as img:
                    lines.append(f"📐 {img.width}\u00d7{img.height}px")
                    if img.format:
                        lines.append(f"🧩 {img.format}")
            except Exception:
                pass

        fmt_global = "" if fmt_var == "Авто" else fmt_var.split(" — ")[0]
        target = fmt_global or resolve_fmt("", ext)
        lines.append(f"→ .{target}  (q={quality}, s={max_size})")

        if result_size > 0:
            ratio = result_size / src_size * 100 if src_size > 0 else 0
            lines.append(f"✅ {fmt_size(result_size)}  ({ratio:.0f}%)  — {result_time}")

        self._info_label.configure(text="\n".join(lines))

    def _refresh_info(self):
        """Легковесное обновление info-текста (без ffmpeg/ffprobe)."""
        if self._current_path and self._last_show_params:
            self._show_info(
                self._current_path,
                self._last_show_params.get("fmt_var", ""),
                self._last_show_params.get("quality", 0),
                self._last_show_params.get("max_size", 0),
                self._last_show_params.get("result_size", 0),
                self._last_show_params.get("result_time", ""),
            )

    # ── Навигация ──

    def _on_prev_clicked(self):
        if self._on_prev:
            self._on_prev()

    def _on_next_clicked(self):
        if self._on_next:
            self._on_next()
