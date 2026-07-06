"""Timeline — обрезка видео/аудио с двумя маркерами IN/OUT + range-drag."""

from __future__ import annotations

import subprocess
import tempfile
import threading
import time
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen, QPixmap, QPolygon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from conv.core import VIDEO_INPUT, Converter, get_media_info
from conv.core import _subprocess_kwargs
from conv.gui.theme import COLORS
from conv.logger import get_logger

log = get_logger("conv.gui.timeline")

TRACK_H = 48
MARKER_W = 3
HANDLE_W = 10
HANDLE_H = 10
MARGIN = 6
COLOR_IN = "#00e676"
COLOR_OUT = "#ff1744"
COLOR_TRACK = "#0f3460"


def _fmt_trim(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    return f"{m:02d}:{s:02d}"


def _fmt_trim2(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    ms = int((sec - int(sec)) * 1000)
    return f"{m:02d}:{s:02d}.{ms:03d}"


def _parse_time(text: str) -> float | None:
    """Парсит время в форматах: 123.5 (сек), MM:SS.mmm, HH:MM:SS.mmm."""
    raw = text.strip().replace(",", ".")
    if not raw:
        return None
    try:
        return abs(float(raw))
    except ValueError:
        pass
    try:
        parts = raw.split(":")
        if len(parts) == 2:
            return abs(int(parts[0])) * 60 + abs(float(parts[1]))
        if len(parts) == 3:
            return abs(int(parts[0])) * 3600 + abs(int(parts[1])) * 60 + abs(float(parts[2]))
    except (ValueError, IndexError):
        pass
    return None


class _TimeInput(QLineEdit):
    """Поле ввода времени MM:SS.mmm. Хранит значение в секундах как float.

    Принимает: 12.5, 1:30.000, 01:30, 0:00:30.500
    """

    valueChanged = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value: float = 0.0
        self._min_val: float = 0.0
        self._max_val: float = 999999.0
        self.setFixedWidth(130)
        self.setAlignment(Qt.AlignCenter)
        self.editingFinished.connect(self._on_editing_finished)

    def setValue(self, val: float) -> None:
        val = max(self._min_val, min(self._max_val, val))
        self._value = val
        self.setText(_fmt_trim2(val))

    def value(self) -> float:
        return self._value

    def setMinimum(self, val: float) -> None:
        self._min_val = val

    def setMaximum(self, val: float) -> None:
        self._max_val = val

    def _on_editing_finished(self) -> None:
        parsed = _parse_time(self.text())
        val = (
            max(self._min_val, min(self._max_val, parsed))
            if parsed is not None
            else self._value
        )
        self._value = val
        self.setText(_fmt_trim2(val))
        self.valueChanged.emit(val)


class _TimelineBar(QWidget):
    """Полоса с двумя маркерами. Затемняются обрезаемые края, центр прозрачен."""

    trim_changed = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(TRACK_H + HANDLE_H + 16)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)

        self._duration: float = 0.0
        self._in_sec: float = 0.0
        self._out_sec: float = 0.0
        self._bg_pixmap: QPixmap | None = None
        self._drag: str | None = None
        self._hover: str | None = None
        self._drag_start_x: float = 0.0
        self._drag_range_len: float = 0.0

    def set_duration(self, sec: float) -> None:
        self._duration = max(0.0, sec)
        self._in_sec = 0.0
        self._out_sec = self._duration
        self._bg_pixmap = None
        self._drag = None
        self.update()

    def set_trim(self, start: float, end: float) -> None:
        self._in_sec = max(0.0, min(start, self._duration))
        self._out_sec = max(0.0, min(end, self._duration))
        self.update()

    def get_trim(self) -> tuple[float, float]:
        return self._in_sec, self._out_sec

    def set_bg_pixmap(self, pixmap: QPixmap | None) -> None:
        self._bg_pixmap = pixmap
        self.update()

    def _track_left(self) -> float:
        return float(MARGIN + HANDLE_W // 2 + 2)

    def _track_right(self) -> float:
        return float(self.width() - MARGIN - HANDLE_W // 2 - 2)

    def _track_width(self) -> float:
        return max(1.0, self._track_right() - self._track_left())

    def _sec_to_x(self, sec: float) -> float:
        if self._duration <= 0:
            return self._track_left()
        return self._track_left() + (sec / self._duration) * self._track_width()

    def _x_to_sec(self, x: float) -> float:
        tw = self._track_width()
        if tw <= 0 or self._duration <= 0:
            return 0.0
        frac = (x - self._track_left()) / tw
        return max(0.0, min(self._duration, frac * self._duration))

    def _hit_marker(self, x: float, sec: float) -> bool:
        cx = self._sec_to_x(sec)
        half = HANDLE_W // 2 + 2
        return (cx - half) <= x <= (cx + half)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self._duration <= 0:
            return
        x = event.position().x()
        for tag, sec in [("in", self._in_sec), ("out", self._out_sec)]:
            if self._hit_marker(x, sec):
                self._drag = tag
                return
        in_x = self._sec_to_x(self._in_sec)
        out_x = self._sec_to_x(self._out_sec)
        if in_x <= x <= out_x:
            self._drag = "range"
            self._drag_start_x = x
            self._drag_range_len = self._out_sec - self._in_sec

    def mouseMoveEvent(self, event):
        x = event.position().x()
        if not self._drag or self._duration <= 0:
            old = self._hover
            self._hover = None
            for _, sec in [("out", self._out_sec), ("in", self._in_sec)]:
                if self._hit_marker(x, sec):
                    self._hover = _, sec
                    break
            if old != self._hover:
                self.setCursor(Qt.ArrowCursor if self._hover is None else Qt.PointingHandCursor)
            return

        if self._drag == "in":
            self._in_sec = max(0.0, min(self._x_to_sec(x), self._out_sec - 0.1))
        elif self._drag == "out":
            self._out_sec = max(self._in_sec + 0.1, min(self._x_to_sec(x), self._duration))
        elif self._drag == "range":
            dx_sec = (x - self._drag_start_x) / self._track_width() * self._duration
            new_in = self._in_sec + dx_sec
            new_out = new_in + self._drag_range_len
            if new_in >= 0 and new_out <= self._duration:
                self._in_sec = new_in
                self._out_sec = new_out
                self._drag_start_x = x

        self.trim_changed.emit(self._in_sec, self._out_sec)
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = None
            self.setCursor(Qt.ArrowCursor)
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        try:
            tl = int(self._track_left())
            tr = int(self._track_right())
            ty = HANDLE_H + 2
            tw = tr - tl

            if self._duration <= 0:
                painter.setPen(QColor(COLORS["text3"]))
                painter.drawText(self.rect(), Qt.AlignCenter, "Нет данных о длительности")
                return

            painter.fillRect(tl, ty, tw, TRACK_H, QColor(COLOR_TRACK))
            if self._bg_pixmap and not self._bg_pixmap.isNull():
                painter.drawPixmap(tl, ty, self._bg_pixmap.scaled(
                    tw, TRACK_H, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))

            in_x = int(self._sec_to_x(self._in_sec))
            out_x = int(self._sec_to_x(self._out_sec))

            # Затемнение ОБРЕЗАЕМЫХ краёв
            if self._in_sec > 0:
                painter.fillRect(tl, ty, in_x - tl, TRACK_H, QColor(0, 0, 0, 191))
            if self._out_sec < self._duration:
                painter.fillRect(out_x, ty, tr - out_x, TRACK_H, QColor(0, 0, 0, 191))

            # Рамки
            painter.setPen(QPen(QColor(COLOR_IN), 2))
            painter.drawLine(in_x, ty, in_x, ty + TRACK_H)
            painter.setPen(QPen(QColor(COLOR_OUT), 2))
            painter.drawLine(out_x, ty, out_x, ty + TRACK_H)

            # Ручки
            self._draw_handle(painter, self._in_sec, COLOR_IN, in_x, ty)
            self._draw_handle(painter, self._out_sec, COLOR_OUT, out_x, ty)

            # Подписи внизу
            painter.setPen(QColor(COLORS["text3"]))
            font = painter.font()
            font.setPointSize(8)
            painter.setFont(font)
            fm = QFontMetrics(font)
            labels = [
                (tl, _fmt_trim(0.0)),
                ((tl + tr) // 2 - 20, _fmt_trim(self._duration / 2)),
                (tr - fm.horizontalAdvance("99:99"), _fmt_trim(self._duration)),
            ]
            for lx, lt in labels:
                painter.drawText(lx, ty + TRACK_H + 15, lt)
        finally:
            painter.end()

    def _draw_handle(self, painter: QPainter, sec: float, color: str,
                     cx: int, ty: int) -> None:
        half = HANDLE_W // 2
        painter.setBrush(QColor(color))
        painter.setPen(Qt.NoPen)
        poly = QPolygon()
        poly.append(QPoint(cx - half, ty))
        poly.append(QPoint(cx + half, ty))
        poly.append(QPoint(cx, ty - HANDLE_H))
        painter.drawPolygon(poly)

        painter.setPen(QColor(color))
        font = painter.font()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        text = _fmt_trim2(sec)
        painter.drawText(cx - QFontMetrics(font).horizontalAdvance(text) // 2,
                         ty - HANDLE_H - 3, text)


class TimelineWidget(QFrame):
    """Виджет обрезки: визуальная шкала + поля ввода IN/OUT."""

    trim_changed = Signal(object, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_path: Path | None = None
        self._duration: float = 0.0
        self._img_dir = Path(tempfile.mkdtemp(prefix="conv_timeline_"))

        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(f"""
            QFrame {{ background-color: {COLORS['surface']};
                      border: 1px solid {COLORS['border']};
                      border-radius: 4px; }}
        """)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        title = QLabel("✂ Обрезка (IN / OUT)")
        title.setStyleSheet("font-weight: bold; color: %s; font-size: 11px; background: transparent;" % COLORS["text"])
        layout.addWidget(title)

        self._bar = _TimelineBar()
        self._bar.trim_changed.connect(self._on_bar_changed)
        layout.addWidget(self._bar)

        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        self._btn_reset = QPushButton("↺ Сброс")
        self._btn_reset.setFixedWidth(80)
        self._btn_reset.clicked.connect(self._reset)
        input_row.addWidget(self._btn_reset)
        input_row.addStretch()

        input_row.addWidget(QLabel("IN:"))
        self._time_in = _TimeInput()
        self._time_in.valueChanged.connect(self._on_time_in_changed)
        input_row.addWidget(self._time_in)

        input_row.addSpacing(12)

        input_row.addWidget(QLabel("OUT:"))
        self._time_out = _TimeInput()
        self._time_out.valueChanged.connect(self._on_time_out_changed)
        input_row.addWidget(self._time_out)

        input_row.addStretch()
        self._dur_label = QLabel("")
        self._dur_label.setStyleSheet("color: %s; background: transparent;" % COLORS["text3"])
        input_row.addWidget(self._dur_label)

        layout.addLayout(input_row)

    def set_file(self, path: Path | None) -> None:
        self._current_path = path
        self._bar.set_duration(0.0)
        self._duration = 0.0
        if path is None:
            self.setVisible(False)
            return
        info = get_media_info(path)
        dur = info.duration or 0.0
        if dur <= 0:
            self.setVisible(False)
            return
        self._duration = dur
        self._bar.set_duration(dur)
        self._update_inputs()
        self._dur_label.setText("⏱ " + _fmt_trim(dur))
        self._generate_background(path, dur)
        self.setVisible(True)

    def get_trim(self, path: Path) -> tuple[float, float]:
        if path == self._current_path and self._duration > 0:
            s, e = self._bar.get_trim()
            return (s, e if e < self._duration else 0.0)
        return (0.0, 0.0)

    def set_trim_silent(self, start: float, end: float) -> None:
        """Установить trim без эмиссии сигнала (восстановление из памяти)."""
        self._bar.trim_changed.disconnect()
        self._time_in.blockSignals(True)
        self._time_out.blockSignals(True)
        self._time_in.setValue(start)
        self._time_out.setValue(end)
        self._time_in.blockSignals(False)
        self._time_out.blockSignals(False)
        self._bar.set_trim(start, end)
        self._bar.trim_changed.connect(self._on_bar_changed)

    def _on_bar_changed(self, start: float, end: float):
        self._time_in.blockSignals(True)
        self._time_out.blockSignals(True)
        self._time_in.setValue(start)
        self._time_out.setValue(end)
        self._time_in.blockSignals(False)
        self._time_out.blockSignals(False)
        self._emit_trim()

    def _on_time_in_changed(self, value: float):
        if self._duration <= 0:
            return
        out_v = self._time_out.value()
        in_val = max(0.0, min(value, out_v - 0.1))
        if abs(in_val - value) > 0.001:
            self._time_in.blockSignals(True)
            self._time_in.setValue(in_val)
            self._time_in.blockSignals(False)
        self._bar.set_trim(in_val, out_v)
        self._emit_trim()

    def _on_time_out_changed(self, value: float):
        if self._duration <= 0:
            return
        in_v = self._time_in.value()
        out_val = max(in_v + 0.1, min(value, self._duration))
        if abs(out_val - value) > 0.001:
            self._time_out.blockSignals(True)
            self._time_out.setValue(out_val)
            self._time_out.blockSignals(False)
        self._bar.set_trim(in_v, out_val)
        self._emit_trim()

    def _reset(self):
        if self._duration > 0:
            self._time_in.blockSignals(True)
            self._time_out.blockSignals(True)
            self._time_in.setValue(0.0)
            self._time_out.setValue(self._duration)
            self._time_in.blockSignals(False)
            self._time_out.blockSignals(False)
            self._bar.set_trim(0.0, self._duration)
            self._emit_trim()

    def _update_inputs(self):
        self._time_in.blockSignals(True)
        self._time_out.blockSignals(True)
        self._time_in.setValue(0.0)
        self._time_out.setValue(self._duration)
        self._time_in.blockSignals(False)
        self._time_out.blockSignals(False)

    def _emit_trim(self):
        if self._current_path:
            s, e = self._bar.get_trim()
            self.trim_changed.emit(self._current_path, s, e)

    # ── Фоновая подложка ──────────────────────────────────────────────

    def _generate_background(self, path: Path, duration: float) -> None:
        def gen():
            self._bar.set_bg_pixmap(self._gen_image(path, duration))
        threading.Thread(target=gen, daemon=True).start()

    def _gen_image(self, path: Path, duration: float) -> QPixmap | None:
        ext = path.suffix.lower()
        ffmpeg = Converter._tool_path("ffmpeg")
        return (self._gen_video_strip(path, ffmpeg) if ext in VIDEO_INPUT
                else self._gen_waveform(path, ffmpeg))

    def _gen_waveform(self, path: Path, ffmpeg: str) -> QPixmap | None:
        out = self._img_dir / f"w{path.stem}_{int(time.time() * 1000)}.png"
        try:
            cs = f"{COLORS['accent'].lstrip('#')}|{COLOR_TRACK.lstrip('#')}"
            r = subprocess.run(
                [ffmpeg, "-i", str(path),
                 "-filter_complex", f"showwavespic=s=800x{TRACK_H}:colors={cs}",
                 "-frames:v", "1", "-y", str(out)],
                capture_output=True, text=True, timeout=30,
                **_subprocess_kwargs(),
            )
            if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
                pix = QPixmap(str(out))
                out.unlink(missing_ok=True)
                return pix if not pix.isNull() else None
        except Exception as e:
            log.debug("waveform err: %s", e)
        return None

    def _gen_video_strip(self, path: Path, ffmpeg: str) -> QPixmap | None:
        out = self._img_dir / f"s{path.stem}_{int(time.time() * 1000)}.png"
        try:
            n = 16
            r = subprocess.run(
                [ffmpeg, "-i", str(path),
                 "-vf", f"fps={n / max(self._duration, 1):.3f},scale=50:-1,tile={n}x1",
                 "-frames:v", "1", "-y", str(out)],
                capture_output=True, text=True, timeout=60,
                **_subprocess_kwargs(),
            )
            if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
                pix = QPixmap(str(out))
                out.unlink(missing_ok=True)
                return pix.scaledToHeight(TRACK_H, Qt.SmoothTransformation) if not pix.isNull() else None
        except Exception as e:
            log.debug("strip err: %s", e)
        return None

    def __del__(self):
        import shutil
        try:
            shutil.rmtree(self._img_dir, ignore_errors=True)
        except Exception:
            pass
