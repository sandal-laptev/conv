"""Timeline — обрезка видео/аудио с двумя маркерами IN/OUT."""

from __future__ import annotations

import math
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
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
TRACK_H = 48          # высота полосы
MARKER_W = 3          # ширина линии маркера
HANDLE_W = 10         # ширина ручки
HANDLE_H = 10         # высота ручки
MARGIN = 6            # отступы от краёв
COLOR_IN = "#00e676"
COLOR_OUT = "#ff1744"
COLOR_TRACK = "#0f3460"
COLOR_SELECTED = "#00d2ff"


class _TimelineBar(QWidget):
    """Кастомный виджет — полоса с двумя перетаскиваемыми маркерами."""

    trim_changed = Signal(float, float)  # start_sec, end_sec

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(TRACK_H + HANDLE_H + 12)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)

        self._duration: float = 0.0
        self._in_sec: float = 0.0
        self._out_sec: float = 0.0
        self._bg_pixmap: QPixmap | None = None

        self._drag: str | None = None  # "in" | "out" | None
        self._hover: str | None = None

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

    def _marker_rect(self, sec: float) -> tuple[float, float, float, float]:
        """(left, top, width, height) области попадания маркера."""
        cx = self._sec_to_x(sec)
        y = 0
        return (cx - HANDLE_W / 2, y, HANDLE_W, HANDLE_H + TRACK_H)

    # ── События мыши ──────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self._duration <= 0:
            return
        x, y = event.position().x(), event.position().y()
        # Проверяем in/out маркеры (от самой верхней точки)
        for tag, sec in [("out", self._out_sec), ("in", self._in_sec)]:
            rx, ry, rw, rh = self._marker_rect(sec)
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                self._drag = tag
                return

    def mouseMoveEvent(self, event):
        x = event.position().x()
        if self._drag and self._duration > 0:
            sec = self._x_to_sec(x)
            if self._drag == "in":
                self._in_sec = max(0.0, min(sec, self._out_sec - 0.1))
            else:
                self._out_sec = max(self._in_sec + 0.1, min(sec, self._duration))
            self.trim_changed.emit(self._in_sec, self._out_sec)
            self.update()
        else:
            # Ховер
            old = self._hover
            self._hover = None
            for tag, sec in [("out", self._out_sec), ("in", self._in_sec)]:
                rx, ry, rw, rh = self._marker_rect(sec)
                if rx <= x <= rx + rw and ry <= event.position().y() <= ry + rh:
                    self._hover = tag
                    break
            if self._hover != old:
                self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = None
            self.update()

    # ── Отрисовка ──────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        tl = self._track_left()
        tr = self._track_right()
        ty = HANDLE_H + 2
        tw = tr - tl

        if self._duration <= 0:
            painter.setPen(QColor(COLORS["text3"]))
            painter.drawText(self.rect(), Qt.AlignCenter, "Нет данных о длительности")
            painter.end()
            return

        # ── Фон дорожки ──
        painter.fillRect(int(tl), ty, int(tw), TRACK_H, QColor(COLOR_TRACK))

        # ── Подложка (waveform/strip) ──
        if self._bg_pixmap and not self._bg_pixmap.isNull():
            scaled = self._bg_pixmap.scaled(
                int(tw), TRACK_H, Qt.IgnoreAspectRatio, Qt.SmoothTransformation,
            )
            painter.drawPixmap(int(tl), ty, scaled)

        # ── Затемнение обрезанных областей ──
        in_x = self._sec_to_x(self._in_sec)
        out_x = self._sec_to_x(self._out_sec)

        if self._in_sec > 0:
            painter.fillRect(
                int(tl), ty, int(in_x - tl), TRACK_H,
                QColor(0, 0, 0, 100),
            )
        if self._out_sec < self._duration:
            painter.fillRect(
                int(out_x), ty, int(tr - out_x), TRACK_H,
                QColor(0, 0, 0, 100),
            )

        # ── Выделенная область ──
        painter.fillRect(
            int(in_x), ty, int(out_x - in_x), TRACK_H,
            QColor(COLOR_SELECTED).lighter(120).lighter(120),
        )

        # ── Маркеры ──
        self._draw_marker(painter, self._in_sec, COLOR_IN, "IN", in_x, ty)
        self._draw_marker(painter, self._out_sec, COLOR_OUT, "OUT", out_x, ty)

        # ── Подписи времени под дорожкой ──
        painter.setPen(QColor(COLORS["text3"]))
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)

        painter.drawText(int(tl), ty + TRACK_H + 14, _fmt_trim(0.0))
        painter.drawText(
            int((tl + tr) / 2 - 30), ty + TRACK_H + 14,
            _fmt_trim(self._duration / 2),
        )
        # OUT label — рисуем от правого края
        out_label = _fmt_trim(self._duration)
        fm = painter.fontMetrics()
        painter.drawText(int(tr - fm.horizontalAdvance(out_label)), ty + TRACK_H + 14, out_label)

        painter.end()

    def _draw_marker(self, painter: QPainter, sec: float, color: str,
                     label: str, x: float, ty: int) -> None:
        cx = int(x)
        y0 = ty
        y1 = ty + TRACK_H
        half = HANDLE_W // 2

        pen = QPen(QColor(color), 2)
        painter.setPen(pen)
        painter.drawLine(cx, y0, cx, y1)

        # Ручка-треугольник
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
        painter.drawText(cx - 40, y0 - HANDLE_H - 3, 80, 12,
                         Qt.AlignCenter, _fmt_trim2(sec))


def _fmt_trim(sec: float) -> str:
    """Форматирует секунды как MM:SS."""
    m, s = divmod(int(sec), 60)
    return f"{m:02d}:{s:02d}"


def _fmt_trim2(sec: float) -> str:
    """Форматирует с миллисекундами: MM:SS.mmm."""
    m, s = divmod(int(sec), 60)
    ms = int((sec - int(sec)) * 1000)
    return f"{m:02d}:{s:02d}.{ms:03d}"


class _TrimSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox с форматированием MM:SS.mmm, диапазон до duration."""

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
        # Парсим MM:SS.mmm или просто число секунд
        try:
            return float(text)
        except ValueError:
            pass
        try:
            parts = text.split(":")
            if len(parts) == 2:
                m, s = parts
                return int(m) * 60 + float(s)
            if len(parts) == 3:
                h, m, s = parts
                return int(h) * 3600 + int(m) * 60 + float(s)
        except (ValueError, IndexError):
            pass
        return self.value()

    def validate(self, text: str, pos: int):
        from PySide6.QtGui import QValidator
        # Accept anything during editing, parse happens on finish
        return (QValidator.Acceptable, text, pos)


class TimelineWidget(QFrame):
    """Виджет обрезки: визуальная шкала + поля ввода IN/OUT.

    Сигналы:
      trim_changed(path: Path, start_sec: float, end_sec: float)
    """

    trim_changed = Signal(object, float, float)  # Path, start, end

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

        # Заголовок
        title = QLabel("✂ Обрезка (IN / OUT)")
        title.setStyleSheet(f"font-weight: bold; color: {COLORS['text']}; "
                            f"font-size: 11px; background: transparent;")
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

        # IN
        input_row.addWidget(QLabel("IN:"))
        self._spin_in = _TrimSpinBox()
        self._spin_in.valueChanged.connect(self._on_spin_in_changed)
        input_row.addWidget(self._spin_in)

        input_row.addSpacing(12)

        # OUT
        input_row.addWidget(QLabel("OUT:"))
        self._spin_out = _TrimSpinBox()
        self._spin_out.valueChanged.connect(self._on_spin_out_changed)
        input_row.addWidget(self._spin_out)

        input_row.addStretch()

        # Длительность
        self._dur_label = QLabel("")
        self._dur_label.setStyleSheet(f"color: {COLORS['text3']}; background: transparent;")
        input_row.addWidget(self._dur_label)

        layout.addLayout(input_row)

    # ── Публичное API ──────────────────────────────────────────────────

    def set_file(self, path: Path | None) -> None:
        """Установить файл и загрузить его длительность."""
        self._current_path = path
        self._bar.set_duration(0.0)
        self._duration = 0.0

        if path is None:
            self.setVisible(False)
            return

        # Получаем длительность
        info = get_media_info(path)
        dur = info.duration or 0.0

        if dur <= 0:
            self.setVisible(False)
            return

        self._duration = dur
        self._bar.set_duration(dur)
        self._update_spins()
        self._dur_label.setText(f"⏱ {_fmt_trim(dur)}")

        # Фоновая генерация waveform/strip
        self._generate_background(path, dur)

        self.setVisible(True)

    def get_trim(self, path: Path) -> tuple[float, float]:
        """Вернуть trim для файла (0, 0 если не настроено)."""
        if path == self._current_path and self._duration > 0:
            start, end = self._bar.get_trim()
            return (start, end if end < self._duration else 0.0)
        return (0.0, 0.0)

    # ── Обработчики ────────────────────────────────────────────────────

    def _on_bar_changed(self, start: float, end: float):
        """Маркеры перемещены на баре."""
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
        """Асинхронно генерирует waveform (аудио) или стрип (видео)."""
        def gen():
            pix = self._gen_image(path, duration)
            if pix:
                # pix.setDevicePixelRatio(1)  # не нужно для QPixmap
                pass
            self._bar.set_bg_pixmap(pix)

        threading.Thread(target=gen, daemon=True).start()

    def _gen_image(self, path: Path, duration: float) -> QPixmap | None:
        """Генерирует подложку: waveform для аудио, стрип для видео."""
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
            n = 16  # число кадров
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
                    # Масштабируем по высоте
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
