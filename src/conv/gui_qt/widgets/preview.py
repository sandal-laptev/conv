"""Preview-панель — миниатюра, навигация, медиа-информация."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image as PILImage
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from conv.core import (
    AUDIO_INPUT,
    VIDEO_INPUT,
    _fmt_size,
    _fmt_time,
    get_media_info,
    resolve_format,
)


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0
from conv.gui_qt.theme import COLORS
from conv.gui_qt.widgets.timeline import TimelineWidget


class _ScaledLabel(QLabel):
    """QLabel, который масштабирует QPixmap под свой размер, сохраняя пропорции."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(200, 150)
        self._pixmap: QPixmap | None = None
        self.setText("(нет превью)")

    def set_image(self, pil_image: PILImage.Image) -> None:
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG")
        qimg = QImage.fromData(buf.getvalue())
        self._pixmap = QPixmap.fromImage(qimg)
        self._scale()

    def clear_image(self) -> None:
        self._pixmap = None
        self.setText("(нет превью)")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._scale()

    def _scale(self) -> None:
        if self._pixmap and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            self.setPixmap(scaled)
        else:
            self.setPixmap(QPixmap())


class PreviewPanel(QWidget):
    """Панель предпросмотра: миниатюра + медиа-инфо + навигация."""

    prev_clicked = Signal()
    next_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_path: Path | None = None
        self._trim_map: dict[Path, tuple[float, float]] = {}
        self._build_ui()
        self.clear()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 0, 0, 0)
        layout.setSpacing(4)

        # ── Заголовок + навигация ──
        nav_row = QHBoxLayout()
        nav_row.setSpacing(4)

        self._nav_label = QLabel("")
        self._nav_label.setStyleSheet(f"color: {COLORS['text2']}; font-size: 11px;")
        nav_row.addWidget(self._nav_label, stretch=1)

        self._btn_prev = QPushButton("◀")
        self._btn_prev.setFixedWidth(30)
        self._btn_prev.clicked.connect(self.prev_clicked.emit)
        nav_row.addWidget(self._btn_prev)

        self._btn_next = QPushButton("▶")
        self._btn_next.setFixedWidth(30)
        self._btn_next.clicked.connect(self.next_clicked.emit)
        nav_row.addWidget(self._btn_next)

        layout.addLayout(nav_row)

        # ── Миниатюра (в QScrollArea на случай большого изображения) ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background-color: {COLORS['bg']}; border: 1px solid {COLORS['border']}; border-radius: 4px; }}
        """)

        self._image_label = _ScaledLabel()
        scroll.setWidget(self._image_label)
        layout.addWidget(scroll, stretch=1)

        # ── Информация о файле ──
        info_frame = QFrame()
        info_frame.setFrameShape(QFrame.StyledPanel)
        info_frame.setStyleSheet(f"""
            QFrame {{ background-color: {COLORS['surface']}; border: 1px solid {COLORS['border']}; border-radius: 4px; }}
            QLabel {{ color: {COLORS['text2']}; font-size: 11px; padding: 1px 4px; }}
        """)
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(6, 4, 6, 4)
        info_layout.setSpacing(1)

        self._info_name = QLabel("")
        self._info_name.setStyleSheet(f"font-weight: bold; color: {COLORS['text']}; font-size: 12px;")
        info_layout.addWidget(self._info_name)

        self._info_lines: list[QLabel] = []
        for _ in range(8):
            lbl = QLabel("")
            info_layout.addWidget(lbl)
            self._info_lines.append(lbl)

        layout.addWidget(info_frame)

        # ── Таймлайн (для видео/аудио) ──
        self._timeline = TimelineWidget()
        self._timeline.trim_changed.connect(self._on_trim_changed)
        self._timeline.setVisible(False)
        layout.addWidget(self._timeline)

    # ── Публичное API ──────────────────────────────────────────────────

    # ── Публичное API ──────────────────────────────────────────────────

    @property
    def current_path(self) -> Path | None:
        return self._current_path

    def get_trim(self, path: Path) -> tuple[float, float]:
        """Вернуть trim (start, end) в секундах для файла. (0, 0) = без обрезки."""
        return self._timeline.get_trim(path)

    def show(self, path: Path, idx: int, total: int,
             fmt_var: str = "", quality: int = 85,
             max_size: int = 0) -> None:
        """Показать предпросмотр для указанного файла."""
        self._current_path = path
        ext = path.suffix.lower()

        # Навигация
        self._nav_label.setText(f"{idx + 1} / {total}")
        self._btn_prev.setEnabled(idx > 0)
        self._btn_next.setEnabled(idx < total - 1)

        # Имя файла
        self._info_name.setText(f"📄 {path.name}")

        # Иконка
        sym = (
            "🎬" if ext in VIDEO_INPUT
            else "🎵" if ext in AUDIO_INPUT
            else "🖼"
        )

        # Общая информация
        size_str = _fmt_size(_file_size(path))
        fmt_out = resolve_format(fmt_var or "", ext)

        lines = [
            f"{sym}  {size_str}  →  .{fmt_out}  (q={quality})",
        ]

        # Медиа-инфо для видео/аудио
        is_media = ext in (VIDEO_INPUT | AUDIO_INPUT)
        if is_media:
            info = get_media_info(path)
            if info.duration:
                lines.append(f"⏱ Длительность: {info.fmt_duration()}")
            if info.bit_rate:
                lines.append(f"📊 Битрейт: {info.fmt_bitrate()}")
            if info.has_video:
                parts = [f"🎞 Видео: {info.video_codec}"]
                if info.resolution_str:
                    parts.append(info.resolution_str)
                if info.fps:
                    parts.append(f"{info.fps:.0f} fps")
                lines.append("  ".join(parts))
            if info.has_audio:
                parts = [f"🎵 Аудио: {info.audio_codec}"]
                ch_map = {"1": "моно", "2": "стерео", "6": "5.1", "8": "7.1"}
                if info.audio_channels:
                    parts.append(ch_map.get(str(info.audio_channels), f"{info.audio_channels}ch"))
                if info.sample_rate:
                    parts.append(f"{info.sample_rate // 1000}kHz")
                lines.append("  ".join(parts))
        else:
            # Изображение — пробуем размеры через PIL
            try:
                with PILImage.open(path) as img:
                    lines.append(f"📐 {img.width}×{img.height}")
            except Exception:
                pass

        # Заполняем строки инфо (очищаем лишние)
        for i, line in enumerate(lines):
            if i < len(self._info_lines):
                self._info_lines[i].setText(line)
        for i in range(len(lines), len(self._info_lines)):
            self._info_lines[i].setText("")

        # Миниатюра для изображений
        try:
            with PILImage.open(path) as img:
                if img.width > 4000 or img.height > 4000:
                    img.thumbnail((4000, 4000), PILImage.LANCZOS)
                self._image_label.set_image(img)
                self._timeline.setVisible(False)
                return
        except Exception:
            pass

        # Для видео/аудио — иконка + таймлайн
        self._image_label.clear_image()
        if is_media:
            self._image_label.setText("🎬\n(предпросмотр видео — с таймлайном ниже)")
            self._timeline.set_file(path)
        else:
            self._image_label.setText("🖼\n(нет превью)")
            self._timeline.setVisible(False)

    def clear(self) -> None:
        """Очистить панель предпросмотра."""
        self._current_path = None
        self._nav_label.setText("— / —")
        self._btn_prev.setEnabled(False)
        self._btn_next.setEnabled(False)
        self._info_name.setText("(нет файла)")
        self._image_label.clear_image()
        self._timeline.set_file(None)
        for lbl in self._info_lines:
            lbl.setText("")

    def _on_trim_changed(self, path: Path, start: float, end: float) -> None:
        self._trim_map[path] = (start, end)
