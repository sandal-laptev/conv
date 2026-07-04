"""Timeline — waveform/кадры + draggable маркеры обрезки (чистый Canvas)."""

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
    VIDEO_INPUT,
    get_media_info,
)
from conv.core import Converter as _Converter
from conv.gui.theme import COLORS, fmt_trim
from conv.logger import get_logger

log = get_logger("conv.timeline")

try:
    from PIL import Image as PILImage, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    PILImage = None
    ImageTk = None

# ── Константы отрисовки ────────────────────────────────────────────────

CANVAS_H = 110         # полная высота Canvas
TIMELINE_Y = 24        # Y начала waveform/стрипа
TIMELINE_H = 72        # высота области волны
MARKER_W = 4           # ширина линии маркера
MARKER_HANDLE_H = 10   # высота ручки маркера
HANDLE_W = 14          # ширина треугольной ручки
MARKER_SNAP = 6        # px — радиус захвата маркера

COLOR_IN = "#00e676"
COLOR_OUT = "#ff1744"
COLOR_PLAYHEAD = "#ffffff"
COLOR_TIME_BG = "#0a0a2e"


class Timeline(ctk.CTkFrame):
    """Интерактивная временная шкала с маркерами обрезки.

    Использует PIL + tkinter.Canvas.
    Для аудио — waveform (showwavespic), для видео — strip кадров.

    Сигналы:
      on_trim_changed(start_sec: float, end_sec: float)
    """

    def __init__(
        self,
        parent,
        on_trim_changed: Callable | None = None,
        **kwargs,
    ):
        super().__init__(parent, fg_color=COLORS["surface2"], **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._on_trim_changed = on_trim_changed
        self._current_path: Path | None = None
        self._duration: float = 0.0

        # Позиции маркеров (в px от левого края Canvas)
        self._in_px: float = 0
        self._out_px: float = 0

        # Состояние drag
        self._drag_target: str | None = None  # "in" | "out"
        self._drag_offset: float = 0.0

        # Canvas
        self._canvas = ctk.CTkCanvas(
            self, height=CANVAS_H,
            bg=COLORS["surface"], highlightthickness=0,
            cursor="hand2",
        )
        self._canvas.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)

        # Привязка мыши
        self._canvas.bind("<Button-1>", self._on_mouse_down)
        self._canvas.bind("<B1-Motion>", self._on_mouse_move)
        self._canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        self._canvas.bind("<Configure>", self._on_resize)

        # Временная папка для сгенерированных изображений
        self._img_dir = Path(tempfile.mkdtemp(prefix="conv_timeline_"))
        self._bg_image: ImageTk.PhotoImage | None = None
        self._bg_image_id: int | None = None
        self._bg_path: Path | None = None  # оригинальный сгенеренный файл
        self._image_duration: float = 0.0  # длительность на момент генерации

        self.bind("<Destroy>", self._cleanup)

    # ── Публичное API ──────────────────────────────────────────────────

    def set_file(self, path: Path | None):
        """Установить файл для отображения на таймлайне."""
        self._cleanup_bg()
        self._current_path = path

        if path is None:
            self._duration = 0.0
            self._redraw()
            return

        info = get_media_info(path)
        self._duration = info.duration or 0.0

        if self._duration <= 0 or not HAS_PIL:
            self._redraw()
            return

        ext = path.suffix.lower()
        cw = max(self._canvas.winfo_width() or 600, 100)
        wave_w = max(cw - 4, 100)

        # Генерируем подложку
        if ext in VIDEO_INPUT:
            bg = self._gen_video_strip(path, wave_w, TIMELINE_H)
        else:
            bg = self._gen_waveform(path, wave_w, TIMELINE_H)

        if bg is None:
            self._redraw()
            return

        try:
            pil_img = PILImage.open(bg)
            tk_img = ImageTk.PhotoImage(pil_img)
            self._bg_image = tk_img
            self._bg_path = bg
            self._image_duration = self._duration
        except Exception as e:
            log.debug("Ошибка загрузки таймлайна: %s", e)
            self._redraw()
            return

        # Сброс маркеров на полный диапазон
        self._in_px = 0
        self._out_px = cw - 4

        self._redraw()

    def set_trim(self, start_sec: float, end_sec: float):
        """Установить позиции маркеров из секунд."""
        cw = max(self._canvas.winfo_width() or 600, 100) - 4
        if self._duration > 0:
            self._in_px = (start_sec / self._duration) * cw if start_sec > 0 else 0
            self._out_px = (end_sec / self._duration) * cw if end_sec > 0 else cw
        else:
            self._in_px = 0
            self._out_px = cw
        self._redraw()

    def get_trim(self) -> tuple[float, float]:
        """Возвращает trim_start/trim_end в секундах."""
        cw = max(self._canvas.winfo_width() or 600, 100) - 4
        if self._duration <= 0 or cw <= 0:
            return (0.0, 0.0)
        start = (self._in_px / cw) * self._duration
        end = (self._out_px / cw) * self._duration
        return (max(0.0, start), min(self._duration, end))

    # ── Генерация подложки ─────────────────────────────────────────────

    def _gen_waveform(self, path: Path, width: int, height: int) -> Path | None:
        """Генерирует waveform изображение через ffmpeg showwavespic."""
        ffmpeg = _Converter._tool_path("ffmpeg")
        if not ffmpeg:
            return None
        out = self._img_dir / f"wave_{path.stem}_{int(time.time())}.png"
        try:
            colors = f"{COLORS['accent'].lstrip('#')}|{COLORS['surface2'].lstrip('#')}"
            r = subprocess.run(
                [ffmpeg, "-i", str(path),
                 "-filter_complex",
                 f"showwavespic=s={width}x{height}:colors={colors}",
                 "-frames:v", "1", "-y", str(out)],
                capture_output=True, text=True, timeout=30,
            )
            if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
                return out
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
            log.debug("waveform err: %s", e)
        return None

    def _gen_video_strip(self, path: Path, width: int, height: int) -> Path | None:
        """Генерирует полоску кадров видео для таймлайна."""
        ffmpeg = _Converter._tool_path("ffmpeg")
        if not ffmpeg or not self._duration:
            return None

        # Извлекаем ~16 кадров равномерно по длительности
        n_frames = min(16, max(4, width // 60))
        fps_val = n_frames / max(self._duration, 1)

        out = self._img_dir / f"strip_{path.stem}_{int(time.time())}.png"
        try:
            r = subprocess.run(
                [ffmpeg, "-i", str(path),
                 "-vf",
                 f"fps={fps_val:.3f},scale={width // n_frames}:-1,"
                 f"tile={n_frames}x1",
                 "-frames:v", "1", "-y", str(out)],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
                # Масштабируем до нужной высоты
                try:
                    img = PILImage.open(out)
                    w_ratio = width / img.width if img.width else 1
                    new_h = int(img.height * w_ratio)
                    if new_h != height:
                        img = img.resize((width, height), PILImage.LANCZOS)
                        img.save(out)
                    return out
                except Exception:
                    if out.exists():
                        return out
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
            log.debug("video strip err: %s", e)
        return None

    # ── Отрисовка ──────────────────────────────────────────────────────

    def _redraw(self):
        """Полная перерисовка Canvas."""
        self._canvas.delete("all")
        cw = max(self._canvas.winfo_width() or 600, 100)
        ch = CANVAS_H

        if self._bg_image:
            self._bg_image_id = self._canvas.create_image(
                2, TIMELINE_Y, anchor="nw", image=self._bg_image,
            )

            # Затемнение области до in и после out
            x1 = 2 + self._in_px
            x2 = 2 + self._out_px

            if self._in_px > 0:
                self._canvas.create_rectangle(
                    2, TIMELINE_Y, x1, TIMELINE_Y + TIMELINE_H,
                    fill="#000000", stipple="gray50", outline="",
                )
            if self._out_px < cw - 4:
                self._canvas.create_rectangle(
                    x2, TIMELINE_Y, cw - 2, TIMELINE_Y + TIMELINE_H,
                    fill="#000000", stipple="gray50", outline="",
                )

            # Маркеры
            self._draw_marker(x1, COLOR_IN, "◀")
            self._draw_marker(x2, COLOR_OUT, "▶")

        else:
            # Нет подложки — рисуем заглушку
            mid_y = TIMELINE_Y + TIMELINE_H // 2
            self._canvas.create_text(
                cw // 2, mid_y, text=self._empty_text(),
                fill=COLORS["text3"], font=("TkFixedFont", 10),
            )

        # Нижняя полоса времени
        self._draw_time_labels(cw)

    def _draw_marker(self, x: float, color: str, arrow: str):
        """Рисует один маркер (линия + треугольная ручка)."""
        y0 = TIMELINE_Y
        y1 = TIMELINE_Y + TIMELINE_H

        # Вертикальная линия
        self._canvas.create_line(x, y0, x, y1, fill=color, width=MARKER_W)

        # Треугольная ручка сверху
        hx = HANDLE_W / 2
        self._canvas.create_polygon(
            x - hx, y0,
            x + hx, y0,
            x, y0 - MARKER_HANDLE_H,
            fill=color, outline=color,
        )

        # Подпись времени
        seconds = self._px_to_sec(x - 2)
        label = fmt_trim(seconds)
        self._canvas.create_text(
            x, y0 - MARKER_HANDLE_H - 2,
            text=label, fill=color,
            font=("TkFixedFont", 8),
            anchor="s",
        )

    def _draw_time_labels(self, cw: int):
        """Рисует метки времени под волной."""
        y = TIMELINE_Y + TIMELINE_H + 2
        labels = []

        # Начало, середина, конец
        if self._duration > 0:
            labels = [
                (2, 0.0),
                (cw // 2, self._duration / 2),
                (cw - 2, self._duration),
            ]
        else:
            labels = [(2, 0.0), (cw - 2, 0.0)]

        for x, sec in labels:
            self._canvas.create_text(
                x, y, text=fmt_trim(sec),
                fill=COLORS["text3"], anchor="nw",
                font=("TkFixedFont", 8),
            )

    def _empty_text(self) -> str:
        """Текст заглушки, если нет подложки."""
        if not self._current_path:
            return ""
        if not HAS_PIL:
            return "PIL не установлен"
        if self._duration <= 0:
            return "Нет данных о длительности"
        return "ffmpeg не найден"

    # ── Конвертация px ↔ секунды ──────────────────────────────────────

    def _px_to_sec(self, px: float) -> float:
        cw = max(self._canvas.winfo_width() or 600, 100) - 4
        if self._duration <= 0 or cw <= 0:
            return 0.0
        return max(0.0, min(self._duration, (px / cw) * self._duration))

    def _sec_to_px(self, sec: float) -> float:
        cw = max(self._canvas.winfo_width() or 600, 100) - 4
        if self._duration <= 0 or cw <= 0:
            return 0.0
        return (sec / self._duration) * cw

    # ── Обработка мыши ─────────────────────────────────────────────────

    def _on_mouse_down(self, event):
        if not self._current_path or self._duration <= 0:
            return

        cx = event.x - 2  # отступ от края

        # Проверяем попадание в маркеры
        if abs(cx - self._in_px) < MARKER_SNAP:
            self._drag_target = "in"
            self._drag_offset = self._in_px - cx
            return
        if abs(cx - self._out_px) < MARKER_SNAP:
            self._drag_target = "out"
            self._drag_offset = self._out_px - cx
            return

        # Клик вне маркеров — ставим playhead (позже)
        self._drag_target = None

    def _on_mouse_move(self, event):
        if self._drag_target is None:
            return

        cw = max(self._canvas.winfo_width() or 600, 100) - 4
        raw_px = event.x - 2 + self._drag_offset

        if self._drag_target == "in":
            self._in_px = max(0, min(raw_px, self._out_px - 2))
        elif self._drag_target == "out":
            self._out_px = max(self._in_px + 2, min(raw_px, cw))

        self._redraw()
        self._emit_trim()

    def _on_mouse_up(self, event):
        if self._drag_target is not None:
            self._drag_target = None
            self._emit_trim()

    def _emit_trim(self):
        if self._on_trim_changed:
            s, e = self.get_trim()
            self._on_trim_changed(s, e)

    # ── Resize ─────────────────────────────────────────────────────────

    def _on_resize(self, event):
        """Перестраиваем при изменении размера."""
        cw = max(event.width, 100) - 4
        # Масштабируем маркеры пропорционально
        if self._duration > 0 and hasattr(self, "_image_duration"):
            # Только масштабируем маркеры, подложку не регенерируем
            old_cw = getattr(self, "_last_cw", cw)
            if old_cw > 0 and old_cw != cw:
                ratio = cw / old_cw
                self._in_px = min(self._in_px * ratio, cw)
                self._out_px = min(self._out_px * ratio, cw)
                # Запоминаем старую ширину
            self._last_cw = cw
        self._redraw()

    # ── Очистка ────────────────────────────────────────────────────────

    def _cleanup_bg(self):
        self._bg_image = None
        self._bg_image_id = None
        if self._bg_path and self._bg_path.exists():
            try:
                self._bg_path.unlink()
            except OSError:
                pass
        self._bg_path = None
        self._image_duration = 0.0

    def _cleanup(self, event=None):
        try:
            shutil.rmtree(self._img_dir, ignore_errors=True)
        except Exception:
            pass
