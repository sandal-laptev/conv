"""Timeline — отображение waveform/кадров + маркеры обрезки (read-only).

Фон генерируется асинхронно в потоке. Маркеры обновляются через set_trim().
Никакой обработки мыши — фейдеры живут в preview.py.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import customtkinter as ctk

from conv.core import (
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

CANVAS_H = 100
TIMELINE_Y = 22
TIMELINE_H = 64
MARKER_W = 3
HANDLE_H = 8
HANDLE_W = 12

COLOR_IN = "#00e676"
COLOR_OUT = "#ff1744"

# Теги Canvas
_T_BG = "bg_img"
_T_DI = "di_"  # dim_in / dim_out
_T_ML = "ml_"  # ml_in / ml_out
_T_MH = "mh_"
_T_MT = "mt_"
_T_TL = "tl_"


class Timeline(ctk.CTkFrame):
    """Визуализация временной шкалы (read-only)."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=COLORS["surface2"], **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._duration: float = 0.0
        self._in_px: float = 0
        self._out_px: float = 0
        self._cw: int = 100
        self._bg_image: ImageTk.PhotoImage | None = None
        self._bg_path: Path | None = None
        self._has_bg = False
        self._img_dir = Path(tempfile.mkdtemp(prefix="conv_timeline_"))

        self._canvas = ctk.CTkCanvas(
            self, height=CANVAS_H,
            bg=COLORS["surface"], highlightthickness=0,
            cursor="arrow",
        )
        self._canvas.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        self._canvas.bind("<Configure>", self._on_resize)
        self.bind("<Destroy>", self._cleanup)

    # ── Публичное API ──────────────────────────────────────────────────

    def set_file(self, path: Path | None):
        """Установить файл (асинхронно, с генерацией подложки в фоне)."""
        self._cleanup_bg()
        if path is None:
            self._duration = 0.0
            self._full_redraw()
            return

        cw = max(self._canvas.winfo_width() or 600, 100)
        self._cw = cw
        self._show_loading()

        def _gen():
            info = get_media_info(path)
            dur = info.duration or 0.0
            if dur <= 0 or not HAS_PIL:
                self.after(0, lambda: self._load_fail(dur))
                return
            ext = path.suffix.lower()
            ww = max(cw - 4, 100)
            bg = (self._gen_video_strip(path, ww, TIMELINE_H)
                  if ext in VIDEO_INPUT
                  else self._gen_waveform(path, ww, TIMELINE_H))
            self.after(0, lambda: self._load_ok(bg, cw, dur))

        threading.Thread(target=_gen, daemon=True).start()

    def set_trim(self, start_sec: float, end_sec: float):
        """Обновить позиции маркеров (в секундах)."""
        cw = max(self._canvas.winfo_width() or 600, 100) - 4
        if self._duration > 0:
            self._in_px = (start_sec / self._duration) * cw if start_sec > 0 else 0
            self._out_px = (end_sec / self._duration) * cw if end_sec > 0 else cw
        else:
            self._in_px = 0
            self._out_px = cw
        self._update()

    # ── Генерация подложки ─────────────────────────────────────────────

    def _gen_waveform(self, path: Path, w: int, h: int) -> Path | None:
        ffmpeg = _Converter._tool_path("ffmpeg")
        if not ffmpeg:
            return None
        out = self._img_dir / f"w{path.stem}_{int(time.time())}.png"
        try:
            cs = f"{COLORS['accent'].lstrip('#')}|{COLORS['surface2'].lstrip('#')}"
            r = subprocess.run(
                [ffmpeg, "-i", str(path),
                 "-filter_complex", f"showwavespic=s={w}x{h}:colors={cs}",
                 "-frames:v", "1", "-y", str(out)],
                capture_output=True, text=True, timeout=30,
            )
            if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
                return out
        except Exception as e:
            log.debug("waveform err: %s", e)
        return None

    def _gen_video_strip(self, path: Path, w: int, h: int) -> Path | None:
        ffmpeg = _Converter._tool_path("ffmpeg")
        if not ffmpeg or not self._duration:
            return None
        n = min(16, max(4, w // 60))
        fps = n / max(self._duration, 1)
        out = self._img_dir / f"s{path.stem}_{int(time.time())}.png"
        try:
            r = subprocess.run(
                [ffmpeg, "-i", str(path),
                 "-vf", f"fps={fps:.3f},scale={w // n}:-1,tile={n}x1",
                 "-frames:v", "1", "-y", str(out)],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
                try:
                    img = PILImage.open(out)
                    r2 = w / img.width if img.width else 1
                    if int(img.height * r2) != h:
                        img = img.resize((w, h), PILImage.LANCZOS).save(out)
                except Exception:
                    pass
                return out
        except Exception as e:
            log.debug("strip err: %s", e)
        return None

    def _load_fail(self, dur: float):
        self._duration = dur
        self._full_redraw()

    def _show_loading(self):
        self._canvas.delete("all")
        cw = max(self._canvas.winfo_width() or 600, 100)
        self._canvas.create_text(
            cw // 2, CANVAS_H // 2,
            text="⏳", fill=COLORS["text3"],
            font=("TkFixedFont", 14),
        )

    def _load_ok(self, bg: Path | None, cw: int, dur: float):
        self._duration = dur
        if bg is None:
            self._full_redraw()
            return
        try:
            self._bg_image = ImageTk.PhotoImage(PILImage.open(bg))
            self._bg_path = bg
            self._has_bg = True
        except Exception as e:
            log.debug("load bg err: %s", e)
            self._full_redraw()
            return
        self._in_px = 0
        self._out_px = cw - 4
        self._full_redraw()

    # ── Отрисовка ──────────────────────────────────────────────────────

    def _full_redraw(self):
        """Полная перерисовка (set_file / resize)."""
        self._canvas.delete("all")
        cw = max(self._canvas.winfo_width() or 600, 100)
        self._cw = cw

        if self._has_bg and self._bg_image:
            self._canvas.create_image(2, TIMELINE_Y, anchor="nw",
                                      image=self._bg_image, tags=_T_BG)
            self._draw_dims(cw)
            self._draw_one(2 + self._in_px, COLOR_IN, _T_ML + "in",
                           _T_MH + "in", _T_MT + "in")
            self._draw_one(2 + self._out_px, COLOR_OUT, _T_ML + "out",
                           _T_MH + "out", _T_MT + "out")
        else:
            self._canvas.create_text(
                cw // 2, CANVAS_H // 2,
                text=self._empty_text(), fill=COLORS["text3"],
                font=("TkFixedFont", 10),
            )

        self._draw_labels(cw)

    def _draw_dims(self, cw: int):
        y0, y1 = TIMELINE_Y, TIMELINE_Y + TIMELINE_H
        x1, x2 = 2 + self._in_px, 2 + self._out_px
        if self._in_px > 0:
            self._canvas.create_rectangle(
                2, y0, x1, y1, fill="#000", stipple="gray50",
                outline="", tags=_T_DI + "in",
            )
        if self._out_px < cw - 4:
            self._canvas.create_rectangle(
                x2, y0, cw - 2, y1, fill="#000", stipple="gray50",
                outline="", tags=_T_DI + "out",
            )

    def _draw_one(self, x: float, color: str, tl, th, tt):
        y0, y1 = TIMELINE_Y, TIMELINE_Y + TIMELINE_H
        hx = HANDLE_W / 2
        self._canvas.create_line(x, y0, x, y1, fill=color, width=MARKER_W, tags=tl)
        self._canvas.create_polygon(
            x - hx, y0, x + hx, y0, x, y0 - HANDLE_H,
            fill=color, outline=color, tags=th,
        )
        sec = self._px2s(x - 2)
        self._canvas.create_text(x, y0 - HANDLE_H - 2, text=fmt_trim(sec),
                                 fill=color, font=("TkFixedFont", 8),
                                 anchor="s", tags=tt)

    def _draw_labels(self, cw: int):
        y = TIMELINE_Y + TIMELINE_H + 2
        pts = [(2, 0.0)]
        if self._duration > 0:
            pts = [(2, 0.0), (cw // 2, self._duration / 2), (cw - 2, self._duration)]
        for i, (x, s) in enumerate(pts):
            self._canvas.create_text(x, y, text=fmt_trim(s),
                                     fill=COLORS["text3"], anchor="nw",
                                     font=("TkFixedFont", 8), tags=_T_TL + str(i))

    # ── Быстрое обновление маркеров ────────────────────────────────────

    def _update(self):
        """Обновить только маркеры + затемнение (coords)."""
        cw = max(self._canvas.winfo_width() or 600, 100)
        if not self._has_bg:
            return
        y0, y1 = TIMELINE_Y, TIMELINE_Y + TIMELINE_H
        x1, x2 = 2 + self._in_px, 2 + self._out_px

        # Dim IN
        if self._in_px > 0:
            self._u_rect(_T_DI + "in", 2, y0, x1, y1)
        else:
            self._canvas.delete(_T_DI + "in")

        # Dim OUT
        if self._out_px < cw - 4:
            self._u_rect(_T_DI + "out", x2, y0, cw - 2, y1)
        else:
            self._canvas.delete(_T_DI + "out")

        # Маркеры
        self._u_one(x1, COLOR_IN, _T_ML + "in", _T_MH + "in", _T_MT + "in")
        self._u_one(x2, COLOR_OUT, _T_ML + "out", _T_MH + "out", _T_MT + "out")

        # Метки
        yl = y1 + 2
        pts = [(2, 0.0)]
        if self._duration > 0:
            pts = [(2, 0.0), (cw // 2, self._duration / 2), (cw - 2, self._duration)]
        for i, (x, s) in enumerate(pts):
            tag = _T_TL + str(i)
            it = self._canvas.find_withtag(tag)
            if it:
                self._canvas.coords(it[0], x, yl)
                self._canvas.itemconfig(it[0], text=fmt_trim(s))

    def _u_rect(self, tag, *coords):
        it = self._canvas.find_withtag(tag)
        if it:
            self._canvas.coords(it[0], *coords)
        else:
            self._canvas.create_rectangle(
                *coords, fill="#000", stipple="gray50", outline="", tags=tag,
            )

    def _u_one(self, x: float, color: str, tl, th, tt):
        y0, y1 = TIMELINE_Y, TIMELINE_Y + TIMELINE_H
        hx = HANDLE_W / 2
        # линия
        it = self._canvas.find_withtag(tl)
        if it:
            self._canvas.coords(it[0], x, y0, x, y1)
        else:
            self._canvas.create_line(x, y0, x, y1, fill=color, width=MARKER_W, tags=tl)
        # ручка
        it = self._canvas.find_withtag(th)
        if it:
            self._canvas.coords(it[0], x - hx, y0, x + hx, y0, x, y0 - HANDLE_H)
        else:
            self._canvas.create_polygon(
                x - hx, y0, x + hx, y0, x, y0 - HANDLE_H,
                fill=color, outline=color, tags=th,
            )
        # текст
        sec = self._px2s(x - 2)
        it = self._canvas.find_withtag(tt)
        if it:
            self._canvas.coords(it[0], x, y0 - HANDLE_H - 2)
            self._canvas.itemconfig(it[0], text=fmt_trim(sec))
        else:
            self._canvas.create_text(
                x, y0 - HANDLE_H - 2, text=fmt_trim(sec), fill=color,
                font=("TkFixedFont", 8), anchor="s", tags=tt,
            )

    # ── Хелперы ────────────────────────────────────────────────────────

    def _empty_text(self):
        if not HAS_PIL:
            return "PIL не установлен"
        if self._duration <= 0:
            return "Нет данных о длительности"
        return "ffmpeg не найден"

    def _px2s(self, px: float) -> float:
        cw = max(self._cw, 100) - 4
        if self._duration <= 0 or cw <= 0:
            return 0.0
        return max(0.0, min(self._duration, (px / cw) * self._duration))

    # ── Resize ─────────────────────────────────────────────────────────

    def _on_resize(self, event):
        cw = max(event.width, 100) - 4
        oc = getattr(self, "_cw", cw)
        if oc > 0 and oc != cw and self._duration > 0:
            r = cw / oc
            self._in_px = min(self._in_px * r, cw)
            self._out_px = min(self._out_px * r, cw)
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
