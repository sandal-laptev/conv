"""Timeline — обрезка видео/аудио с двумя маркерами IN/OUT + range-drag."""

from __future__ import annotations

import subprocess
import tempfile
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from conv.core import VIDEO_INPUT, Converter, get_media_info
from conv.gui_qt.theme import COLORS
from conv.logger import get_logger

log = get_logger("conv.gui_qt.timeline")

# Константы отрисовки
TRACK_H = 48
MARKER_W = 3
HANDLE_W = 10
HANDLE_H = 10
MARGIN = 6
COLOR_IN = "#00e676"        # зелёный — IN
COLOR_OUT = "#ff1744"       # красный — OUT
COLOR_TRACK = "#0f3460"     # фон дорожки
COLOR_CUT = "#000000"       # затемнение обрезаемого


def _fmt_trim(sec: float) -> str:
    """MM:SS."""
    m, s = divmod(int(sec), 60)
    return f"{m:02d}:{s:02d}"


def _fmt_trim2(sec: float) -> str:
    """MM:SS.mmm."""
    m, s = divmod(int(sec), 60)
    ms = int((sec - int(sec)) * 1000)
    return f"{m:02d}:{s:02d}.{ms:03d}"


class _TimelineBar(QWidget):
    """Кастомный виджет — полоса с двумя перетаскиваемыми маркерами.

    ✅ Затемняются обрезаемые области (по краям), центральный сегмент прозрачен.
    ✅ Range-drag: перетаскивание за центр перемещает оба маркера вместе.
    """

    trim_changed = Signal(float, float)  # start_sec, end_sec

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(TRACK_H + HANDLE_H + 16)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)

        self._duration: float = 0.0
        self._in_sec: float = 0.0
        self._out_sec: float = 0.0
        self._bg_pixmap: QPixmap | None = None

        self._drag: str | None = None  # "in" | "out" | "range" | None
        self._hover: str | None = None
        self._drag_start_x: float = 0.0
        self._drag_range_len: float = 0.0

    # ── Публичное API ──────────────────────────────────────────────────

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

    # ── Координаты ─────────────────────────────────────────────────────

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

    # ── События мыши ──────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self._duration <= 0:
            return
        x = event.position().x()

        # Приоритет: маркер IN → маркер OUT → центр (range-drag)
        for tag, sec in [("in", self._in_sec), ("out", self._out_sec)]:
            if self._hit_marker(x, sec):
                self._drag = tag
                return

        # Между IN и OUT — range-drag
        in_x = self._sec_to_x(self._in_sec)
        out_x = self._sec_to_x(self._out_sec)
        if in_x <= x <= out_x:
            self._drag = "range"
            self._drag_start_x = x
            self._drag_range_len = self._out_sec - self._in_sec

    def mouseMoveEvent(self, event):
        x = event.position().x()
        if not self._drag or self._duration <= 0:
            # Ховер
            old = self._hover
            self._hover = None
            for tag, sec in [("out", self._out_sec), ("in", self._in_sec)]:
                if self._hit_marker(x, sec):
                    self._hover = tag
                    break
            if old != self._hover and old is not None:
                self.setCursor(Qt.ArrowCursor if self._hover is None
                               else Qt.PointingHandCursor)
            return

        if self._drag == "in":
            sec = self._x_to_sec(x)
            self._in_sec = max(0.0, min(sec, self._out_sec - 0.1))
        elif self._drag == "out":
            sec = self._x_to_sec(x)
            self._out_sec = max(self._in_sec + 0.1, min(sec, self._duration))
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

    def _hit_marker(self, x: float, sec: float) -> bool:
        """Попадание в зону маркера (широкую — HANDLE_W + 4px)."""
        cx = self._sec_to_x(sec)
        half = HANDLE_W // 2 + 2
        return (cx - half) <= x <= (cx + half)

    # ── Отрисовка ──────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        w = self.width()
        tl = self._track_left()
        tr = self._track_right()
        ty = HANDLE_H + 2
        tw = tr - tl

        if self._duration <= 0:
            painter.setPen(QColor(COLORS["text3"]))
            painter.drawText(self.rect(), Qt.AlignCenter,
                             "Нет данных о длительности")
            painter.end()
            return

        # ── Подложка (waveform/strip) ──
        painter.fillRect(int(tl), ty, int(tw), TRACK_H, QColor(COLOR_TRACK))
        if self._bg_pixmap and not self._bg_pixmap.isNull():
            scaled = self._bg_pixmap.scaled(
                int(tw), TRACK_H, Qt.IgnoreAspectRatio, Qt.SmoothTransformation,
            )
            painter.drawPixmap(int(tl), ty, scaled)

        # ── Координаты маркеров ──
        in_x = self._sec_to_x(self._in_sec)
        out_x = self._sec_to_x(self._out_sec)

        # ── Затемнение ОБРЕЗАЕМЫХ областей (существенное) ──
        # Слева от IN: обрезается → чёрный с 75%
        if self._in_sec > 0:
            painter.fillRect(int(tl), ty, int(in_x - tl), TRACK_H,
                             QColor(0, 0, 0, 191))  # 75%

        # Справа от OUT: обрезается → чёрный с 75%
        if self._out_sec < self._duration:
            painter.fillRect(int(out_x), ty, int(tr - out_x), TRACK_H,
                             QColor(0, 0, 0, 191))  # 75%

        # ── Тонкая рамка IN/OUT для ясности ──
        painter.setPen(QPen(QColor(COLOR_IN), 2))
        painter.drawLine(int(in_x), ty, int(in_x), ty + TRACK_H)
        painter.setPen(QPen(QColor(COLOR_OUT), 2))
        painter.drawLine(int(out_x), ty, int(out_x), ty + TRACK_H)

        # ── Маркеры-ручки ──
        self._draw_handle(painter, self._in_sec, COLOR_IN, "IN", in_x, ty)
        self._draw_handle(painter, self._out_sec, COLOR_OUT, "OUT", out_x, ty)

        # ── Подписи времени ──
        painter.setPen(QColor(COLORS["text3"]))
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        fm = QFontMetrics(font)

        labels = [
            (int(tl), _fmt_trim(0.0)),
            (int((tl + tr) / 2 - 20), _fmt_trim(self._duration / 2)),
            (int(tr - fm.horizontalAdvance("99:99")), _fmt_trim(self._duration)),
        ]
        for lx, ltxt in labels:
            painter.drawText(lx, ty + TRACK_H + 15, ltxt)

        painter.end()

    def _draw_handle(self, painter: QPainter, sec: float, color: str,
                     label: str, cx: int, ty: int) -> None:
        half = HANDLE_W // 2
        y0 = ty

        # Треугольник-ручка
        painter.setBrush(QColor(color))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon([
            (cx - half, y0),
            (cx + half, y0),
            (cx, y0 - HANDLE_H),
        ])

        # Метка времени над ручкой
        painter.setPen(QColor(color))
        font = painter.font()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        fm = QFontMetrics(font)
        text = _fmt_trim2(sec)
        tw = fm.horizontalAdvance(text)
        painter.drawText(cx - tw // 2, y0 - HANDLE_H - 3, text)


class _TrimSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox с форматированием MM:SS.mmm."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDecimals(3)
        self.setRange(0.0, 999999.0)
        self.setSingleStep(0.5)
        self.setSuffix(" с")
        self.setGroupSeparatorShown(False)
        self.setFixedWidth(130)

    def textFromValue(self, value: float) -> str:
        return _fmt_trim2(value)

    def valueFromText(self, text: str) -> float:
        try:
            return float(text)
        except ValueError:
            pass
        try:
            parts = text.split(":")
            if len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        except (ValueError, IndexError):
            pass
        return self.value()

    def validate(self, text: str, pos: int):
        from PySide6.QtGui import QValidator
        return (QValidator.Acceptable, text, pos)


class TimelineWidget(QFrame):
    """Виджет обрезки: визуальная шкала + поля ввода IN/OUT.

    Сигналы:
      trim_changed(path: Path, start_sec: float, end_sec: float)
    """

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
        title.setStyleSheet(
            f"font-weight: bold; color: {COLORS['text']}; "
            f"font-size: 11px; background: transparent;"
        )
        layout.addWidget(title)

        # Полоса
        self._bar = _TimelineBar()
        self._bar.trim_changed.connect(self._on_bar_changed)
        layout.addWidget(self._bar)

        # Поля ввода + кнопки
        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        self._btn_reset = QPushButton("↺ Сброс")
        self._btn_reset.setFixedWidth(80)
        self._btn_reset.clicked.connect(self._reset)
        input_row.addWidget(self._btn_reset)

        input_row.addStretch()

        input_row.addWidget(QLabel("IN:"))
        self._spin_in = _TrimSpinBox()
        self._spin_in.valueChanged.connect(self._on_spin_in_changed)
        input_row.addWidget(self._spin_in)

        input_row.addSpacing(12)

        input_row.addWidget(QLabel("OUT:"))
        self._spin_out = _TrimSpinBox()
        self._spin_out.valueChanged.connect(self._on_spin_out_changed)
        input_row.addWidget(self._spin_out)

        input_row.addStretch()

        self._dur_label = QLabel("")
        self._dur_label.setStyleSheet(
            f"color: {COLORS['text3']}; background: transparent;"
        )
        input_row.addWidget(self._dur_label)

        layout.addLayout(input_row)

    # ── Публичное API ──────────────────────────────────────────────────

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
        self._update_spins()
        self._dur_label.setText(f"⏱ {_fmt_trim(dur)}")
        self._generate_background(path, dur)
        self.setVisible(True)

    def get_trim(self, path: Path) -> tuple[float, float]:
        if path == self._current_path and self._duration > 0:
            start, end = self._bar.get_trim()
            return (start, end if end < self._duration else 0.0)
        return (0.0, 0.0)

    # ── Обработчики ────────────────────────────────────────────────────

    def _on_bar_changed(self, start: float, end: float):
        self._spin_in.blockSignals(True)
        self._spin_out.blockSignals(True)
        self._spin_in.setValue(start)
        self._spin_out.setValue(end)
        self._spin_in.blockSignals(False)
        self._spin_out.blockSignals(False)
        self._emit_trim()

    def _on_spin_in_changed(self, value: float):
        if self._duration <= 0:
            return
        in_val = max(0.0, min(value, self._spin_out.value() - 0.1))
        if abs(in_val - value) > 0.001:
            self._spin_in.blockSignals(True)
            self._spin_in.setValue(in_val)
            self._spin_in.blockSignals(False)
        self._spin_out.setMinimum(in_val + 0.1)
        self._bar.set_trim(in_val, self._spin_out.value())
        self._emit_trim()

    def _on_spin_out_changed(self, value: float):
        if self._duration <= 0:
            return
        out_val = max(self._spin_in.value() + 0.1, min(value, self._duration))
        if abs(out_val - value) > 0.001:
            self._spin_out.blockSignals(True)
            self._spin_out.setValue(out_val)
            self._spin_out.blockSignals(False)
        self._spin_in.setMaximum(out_val - 0.1)
        self._bar.set_trim(self._spin_in.value(), out_val)
        self._emit_trim()

    def _reset(self):
        if self._duration > 0:
            self._spin_in.blockSignals(True)
            self._spin_out.blockSignals(True)
            self._spin_in.setValue(0.0)
            self._spin_out.setValue(self._duration)
            self._spin_in.setMaximum(self._duration)
            self._spin_out.setMinimum(0.0)
            self._spin_in.blockSignals(False)
            self._spin_out.blockSignals(False)
            self._bar.set_trim(0.0, self._duration)
            self._emit_trim()

    def _update_spins(self):
        self._spin_in.blockSignals(True)
        self._spin_out.blockSignals(True)
        self._spin_in.setRange(0.0, self._duration)
        self._spin_in.setValue(0.0)
        self._spin_out.setRange(0.0, self._duration)
        self._spin_out.setValue(self._duration)
        self._spin_in.blockSignals(False)
        self._spin_out.blockSignals(False)

    def _emit_trim(self):
        if self._current_path:
            start, end = self._bar.get_trim()
            self.trim_changed.emit(self._current_path, start, end)

    # ── Фоновая подложка ───────────────────────────────────────────────

    def _generate_background(self, path: Path, duration: float) -> None:
        def gen():
            pix = self._gen_image(path, duration)
            self._bar.set_bg_pixmap(pix)
        threading.Thread(target=gen, daemon=True).start()

    def _gen_image(self, path: Path, duration: float) -> QPixmap | None:
        ext = path.suffix.lower()
        ffmpeg = Converter._tool_path("ffmpeg")
        if ext in VIDEO_INPUT:
            return self._gen_video_strip(path, ffmpeg)
        else:
            return self._gen_waveform(path, ffmpeg)

    def _gen_waveform(self, path: Path, ffmpeg: str) -> QPixmap | None:
        out = self._img_dir / f"w{path.stem}_{int(time.time() * 1000)}.png"
        try:
            cs = f"{COLORS['accent'].lstrip('#')}|{COLOR_TRACK.lstrip('#')}"
            r = subprocess.run(
                [ffmpeg, "-i", str(path),
                 "-filter_complex", f"showwavespic=s=800x{TRACK_H}:colors={cs}",
                 "-frames:v", "1", "-y", str(out)],
                capture_output=True, text=True, timeout=30,
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
            fps = n / max(self._duration, 1)
            r = subprocess.run(
                [ffmpeg, "-i", str(path),
                 "-vf", f"fps={fps:.3f},scale=50:-1,tile={n}x1",
                 "-frames:v", "1", "-y", str(out)],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
                pix = QPixmap(str(out))
                out.unlink(missing_ok=True)
                if not pix.isNull():
                    return pix.scaledToHeight(TRACK_H, Qt.SmoothTransformation)
            return None
        except Exception as e:
            log.debug("strip err: %s", e)
        return None

    def __del__(self):
        import shutil
        try:
            shutil.rmtree(self._img_dir, ignore_errors=True)
        except Exception:
            pass
