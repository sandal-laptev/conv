"""Timeline — waveform/кадры + draggable маркеры обрезки (чистый Canvas).

Оптимизация: фон рисуется 1 раз, маркеры двигаются через coords() без delete("all").
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
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

CANVAS_H = 110
TIMELINE_Y = 24
TIMELINE_H = 72
MARKER_W = 4
MARKER_HANDLE_H = 10
HANDLE_W = 14
MARKER_SNAP = 6

COLOR_IN = "#00e676"
COLOR_OUT = "#ff1744"

# Теги Canvas для быстрого поиска элементов
T_BG = "bg_img"
T_DIM_IN = "dim_in"
T_DIM_OUT = "dim_out"
T_ML_IN = "ml_in"
T_MH_IN = "mh_in"
T_MLBL_IN = "mlbl_in"
T_ML_OUT = "ml_out"
T_MH_OUT = "mh_out"
T_MLBL_OUT = "mlbl_out"
T_TL = "tlabel_"
T_PLACEHOLDER = "ph"


class Timeline(ctk.CTkFrame):
    """Интерактивная временная шкала с маркерами обрезки.

    Для аудио — waveform (showwavespic), для видео — strip кадров.
    Drag обновляет только маркеры + затемнение, без перерисовки фона.
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
        self._in_px: float = 0
        self._out_px: float = 0
        self._drag_target: str | None = None
        self._drag_offset: float = 0.0
        self._cw: int = 100               # кешированная ширина Canvas
        self._bg_image: ImageTk.PhotoImage | None = None
        self._bg_path: Path | None = None
        self._img_dir = Path(tempfile.mkdtemp(prefix="conv_timeline_"))
        self._has_bg = False

        self._canvas = ctk.CTkCanvas(
            self, height=CANVAS_H,
            bg=COLORS["surface"], highlightthickness=0,
            cursor="hand2",
        )
        self._canvas.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)

        self._canvas.bind("<Button-1>", self._on_mouse_down)
        self._canvas.bind("<B1-Motion>", self._on_mouse_move)
        self._canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        self._canvas.bind("<Configure>", self._on_resize)

        self.bind("<Destroy>", self._cleanup)

    # ── Публичное API ──────────────────────────────────────────────────

    def set_file(self, path: Path | None):
        """Установить файл для отображения (полностью асинхронно)."""
        self._cleanup_bg()
        self._current_path = path

        if path is None:
            self._duration = 0.0
            self._full_redraw()
            return

        cw = max(self._canvas.winfo_width() or 600, 100)
        self._cw = cw
        self._show_loading()

        # Всё в фоне: ffprobe + ffmpeg генерация
        def _generate():
            info = get_media_info(path)
            duration = info.duration or 0.0
            if duration <= 0 or not HAS_PIL:
                self.after(0, lambda: self._on_bg_fail(duration))
                return

            ext = path.suffix.lower()
            wave_w = max(cw - 4, 100)
            if ext in VIDEO_INPUT:
                bg = self._gen_video_strip(path, wave_w, TIMELINE_H)
            else:
                bg = self._gen_waveform(path, wave_w, TIMELINE_H)
            self.after(0, lambda: self._on_bg_generated(bg, cw, duration))

        threading.Thread(target=_generate, daemon=True).start()

    def _on_bg_fail(self, duration: float):
        """Фоновая генерация не удалась."""
        self._duration = duration
        self._full_redraw()

    def _show_loading(self):
        """Показывает заглушку загрузки."""
        self._canvas.delete("all")
        cw = max(self._canvas.winfo_width() or 600, 100)
        self._canvas.create_text(
            cw // 2, TIMELINE_Y + TIMELINE_H // 2,
            text="⏳ Генерация таймлайна…",
            fill=COLORS["text3"], font=("TkFixedFont", 10),
            tags=T_PLACEHOLDER,
        )

    def _on_bg_generated(self, bg_path: Path | None, cw: int, duration: float):
        """Коллбэк после завершения генерации в фоне."""
        self._duration = duration
        if bg_path is None:
            self._full_redraw()
            return
        try:
            pil_img = PILImage.open(bg_path)
            tk_img = ImageTk.PhotoImage(pil_img)
            self._bg_image = tk_img
            self._bg_path = bg_path
            self._has_bg = True
        except Exception as e:
            log.debug("Ошибка загрузки таймлайна: %s", e)
            self._full_redraw()
            return

        self._in_px = 0
        self._out_px = cw - 4
        self._full_redraw()

    def set_trim(self, start_sec: float, end_sec: float):
        """Установить позиции маркеров из секунд."""
        cw = max(self._canvas.winfo_width() or 600, 100) - 4
        if self._duration > 0:
            self._in_px = (start_sec / self._duration) * cw if start_sec > 0 else 0
            self._out_px = (end_sec / self._duration) * cw if end_sec > 0 else cw
        else:
            self._in_px = 0
            self._out_px = cw
        self._redraw_markers()

    def get_trim(self) -> tuple[float, float]:
        """Возвращает trim_start/trim_end в секундах."""
        cw = max(self._canvas.winfo_width() or 600, 100) - 4
        if self._duration <= 0 or cw <= 0:
            return (0.0, 0.0)
        s = (self._in_px / cw) * self._duration
        e = (self._out_px / cw) * self._duration
        return (max(0.0, s), min(self._duration, e))

    # ── Генерация подложки ─────────────────────────────────────────────

    def _gen_waveform(self, path: Path, width: int, height: int) -> Path | None:
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
        ffmpeg = _Converter._tool_path("ffmpeg")
        if not ffmpeg or not self._duration:
            return None
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
        except Exception as e:
            log.debug("video strip err: %s", e)
        return None

    # ── Полная отрисовка (1 раз при загрузке файла / ресайзе) ──────────

    def _full_redraw(self):
        """Рисует ВСЁ с нуля. Вызывается при set_file() и resize()."""
        self._canvas.delete("all")
        cw = max(self._canvas.winfo_width() or 600, 100)
        self._cw = cw

        if self._has_bg and self._bg_image:
            # Подложка
            self._canvas.create_image(
                2, TIMELINE_Y, anchor="nw", image=self._bg_image,
                tags=T_BG,
            )
            # Затемнение + маркеры + метки
            self._draw_dim_areas(cw)
            self._draw_marker(2 + self._in_px, COLOR_IN, T_ML_IN, T_MH_IN, T_MLBL_IN)
            self._draw_marker(2 + self._out_px, COLOR_OUT, T_ML_OUT, T_MH_OUT, T_MLBL_OUT)
        else:
            # Заглушка
            mid_y = TIMELINE_Y + TIMELINE_H // 2
            self._canvas.create_text(
                cw // 2, mid_y, text=self._empty_text(),
                fill=COLORS["text3"], font=("TkFixedFont", 10),
                tags=T_PLACEHOLDER,
            )

        self._draw_time_labels(cw)

    def _draw_dim_areas(self, cw: int):
        """Рисует затемнённые области до in и после out."""
        x1 = 2 + self._in_px
        x2 = 2 + self._out_px
        y0, y1 = TIMELINE_Y, TIMELINE_Y + TIMELINE_H

        if self._in_px > 0:
            self._canvas.create_rectangle(
                2, y0, x1, y1,
                fill="#000000", stipple="gray50", outline="",
                tags=T_DIM_IN,
            )
        if self._out_px < cw - 4:
            self._canvas.create_rectangle(
                x2, y0, cw - 2, y1,
                fill="#000000", stipple="gray50", outline="",
                tags=T_DIM_OUT,
            )

    def _draw_marker(self, x: float, color: str,
                     tag_line: str, tag_hand: str, tag_lbl: str):
        """Рисует один маркер с тегами."""
        y0, y1 = TIMELINE_Y, TIMELINE_Y + TIMELINE_H
        hx = HANDLE_W / 2

        self._canvas.create_line(x, y0, x, y1, fill=color, width=MARKER_W,
                                 tags=tag_line)
        self._canvas.create_polygon(
            x - hx, y0, x + hx, y0, x, y0 - MARKER_HANDLE_H,
            fill=color, outline=color, tags=tag_hand,
        )
        sec = self._px_to_sec(x - 2)
        self._canvas.create_text(
            x, y0 - MARKER_HANDLE_H - 2,
            text=fmt_trim(sec), fill=color,
            font=("TkFixedFont", 8), anchor="s",
            tags=tag_lbl,
        )

    def _draw_time_labels(self, cw: int):
        """Рисует метки времени под волной (с тегами)."""
        y = TIMELINE_Y + TIMELINE_H + 2
        points = [(2, 0.0)]
        if self._duration > 0:
            points = [
                (2, 0.0),
                (cw // 2, self._duration / 2),
                (cw - 2, self._duration),
            ]
        for i, (x, sec) in enumerate(points):
            self._canvas.create_text(
                x, y, text=fmt_trim(sec),
                fill=COLORS["text3"], anchor="nw",
                font=("TkFixedFont", 8),
                tags=f"{T_TL}{i}",
            )

    # ── Быстрое обновление маркеров (без delete("all")!) ──────────────

    def _redraw_markers(self):
        """Обновляет только позиции маркеров + затемнение.

        Использует canvas.coords() вместо delete+create.
        """
        cw = max(self._canvas.winfo_width() or 600, 100)
        y0, y1 = TIMELINE_Y, TIMELINE_Y + TIMELINE_H

        if not self._has_bg:
            return

        # ── Затемнение ────────────────────────────────────────────────
        x1 = 2 + self._in_px
        x2 = 2 + self._out_px

        # IN-dimmer
        if self._in_px > 0:
            items_in = self._canvas.find_withtag(T_DIM_IN)
            if items_in:
                self._canvas.coords(items_in[0], 2, y0, x1, y1)
            else:
                self._canvas.create_rectangle(
                    2, y0, x1, y1,
                    fill="#000000", stipple="gray50", outline="",
                    tags=T_DIM_IN,
                )
        else:
            self._canvas.delete(T_DIM_IN)

        # OUT-dimmer
        if self._out_px < cw - 4:
            items_out = self._canvas.find_withtag(T_DIM_OUT)
            if items_out:
                self._canvas.coords(items_out[0], x2, y0, cw - 2, y1)
            else:
                self._canvas.create_rectangle(
                    x2, y0, cw - 2, y1,
                    fill="#000000", stipple="gray50", outline="",
                    tags=T_DIM_OUT,
                )
        else:
            self._canvas.delete(T_DIM_OUT)

        # ── Маркер IN ─────────────────────────────────────────────────
        self._move_marker(x1, T_ML_IN, T_MH_IN, T_MLBL_IN, COLOR_IN)

        # ── Маркер OUT ────────────────────────────────────────────────
        self._move_marker(x2, T_ML_OUT, T_MH_OUT, T_MLBL_OUT, COLOR_OUT)

        # ── Метки времени ────────────────────────────────────────────
        y_label = y1 + 2
        points = [(2, 0.0)]
        if self._duration > 0:
            points = [
                (2, 0.0),
                (cw // 2, self._duration / 2),
                (cw - 2, self._duration),
            ]
        for i, (x, sec) in enumerate(points):
            tag = f"{T_TL}{i}"
            items = self._canvas.find_withtag(tag)
            if items:
                self._canvas.coords(items[0], x, y_label)
                self._canvas.itemconfig(items[0], text=fmt_trim(sec))

    def _move_marker(self, x: float,
                     tag_line: str, tag_hand: str, tag_lbl: str,
                     color: str):
        """Перемещает существующий маркер или создаёт, если нет."""
        y0, y1 = TIMELINE_Y, TIMELINE_Y + TIMELINE_H
        hx = HANDLE_W / 2

        # Линия
        items = self._canvas.find_withtag(tag_line)
        if items:
            self._canvas.coords(items[0], x, y0, x, y1)
        else:
            self._canvas.create_line(x, y0, x, y1, fill=color,
                                     width=MARKER_W, tags=tag_line)

        # Ручка (треугольник)
        items = self._canvas.find_withtag(tag_hand)
        if items:
            self._canvas.coords(items[0], x - hx, y0, x + hx, y0, x, y0 - MARKER_HANDLE_H)
        else:
            self._canvas.create_polygon(
                x - hx, y0, x + hx, y0, x, y0 - MARKER_HANDLE_H,
                fill=color, outline=color, tags=tag_hand,
            )

        # Подпись
        sec = self._px_to_sec(x - 2)
        items = self._canvas.find_withtag(tag_lbl)
        if items:
            self._canvas.coords(items[0], x, y0 - MARKER_HANDLE_H - 2)
            self._canvas.itemconfig(items[0], text=fmt_trim(sec))
        else:
            self._canvas.create_text(
                x, y0 - MARKER_HANDLE_H - 2,
                text=fmt_trim(sec), fill=color,
                font=("TkFixedFont", 8), anchor="s",
                tags=tag_lbl,
            )

    # ── Заглушка ──────────────────────────────────────────────────────

    def _empty_text(self) -> str:
        if not self._current_path:
            return ""
        if not HAS_PIL:
            return "PIL не установлен"
        if self._duration <= 0:
            return "Нет данных о длительности"
        return "ffmpeg не найден"

    # ── Конвертация px ↔ секунды ──────────────────────────────────────

    def _px_to_sec(self, px: float) -> float:
        cw = max(self._cw, 100) - 4
        if self._duration <= 0 or cw <= 0:
            return 0.0
        return max(0.0, min(self._duration, (px / cw) * self._duration))

    def _sec_to_px(self, sec: float) -> float:
        cw = max(self._cw, 100) - 4
        if self._duration <= 0 or cw <= 0:
            return 0.0
        return (sec / self._duration) * cw

    # ── Обработка мыши ─────────────────────────────────────────────────

    def _on_mouse_down(self, event):
        if not self._current_path or self._duration <= 0 or not self._has_bg:
            return
        cx = event.x - 2
        if abs(cx - self._in_px) < MARKER_SNAP:
            self._drag_target = "in"
            self._drag_offset = self._in_px - cx
            return
        if abs(cx - self._out_px) < MARKER_SNAP:
            self._drag_target = "out"
            self._drag_offset = self._out_px - cx
            return

    def _on_mouse_move(self, event):
        if self._drag_target is None:
            return
        cw = max(self._canvas.winfo_width() or 600, 100) - 4
        raw_px = event.x - 2 + self._drag_offset

        if self._drag_target == "in":
            self._in_px = max(0, min(raw_px, self._out_px - 2))
        elif self._drag_target == "out":
            self._out_px = max(self._in_px + 2, min(raw_px, cw))

        # ❗ Только маркеры + затемнение — без delete("all")
        self._redraw_markers()
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
        """Пересчёт маркеров + полная перерисовка (подложку не регенерируем)."""
        cw = max(event.width, 100) - 4
        old_cw = getattr(self, "_cw", cw)
        if old_cw > 0 and old_cw != cw and self._duration > 0:
            ratio = cw / old_cw
            self._in_px = min(self._in_px * ratio, cw)
            self._out_px = min(self._out_px * ratio, cw)
        self._cw = cw
        self._full_redraw()

    # ── Очистка ────────────────────────────────────────────────────────

    def _cleanup_bg(self):
        self._bg_image = None
        self._has_bg = False
        if self._bg_path and self._bg_path.exists():
            try:
                self._bg_path.unlink()
            except OSError:
                pass
        self._bg_path = None

    def _cleanup(self, event=None):
        try:
            shutil.rmtree(self._img_dir, ignore_errors=True)
        except Exception:
            pass
