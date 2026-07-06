"""Preview-панель — миниатюра, видеоплеер (с обрезкой), медиа-инфо, таймлайн."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image as PILImage
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from conv.core import AUDIO_INPUT, VIDEO_INPUT, _fmt_size, get_media_info, resolve_format
from conv.gui_qt.theme import COLORS
from conv.gui_qt.widgets.timeline import TimelineWidget


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


class _ScaledLabel(QLabel):
    """QLabel с масштабированием QPixmap под размер."""

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


class _VideoPlayerWidget(QWidget):
    """Виджет видео с поддержкой playbackRange (обрезка на лету)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._user_dragging = False
        self._range_start_ms: int = 0
        self._range_end_ms: int = -1  # -1 = до конца
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._video_widget = QVideoWidget()
        self._player.setVideoOutput(self._video_widget)
        self._video_widget.setMinimumSize(200, 150)
        self._video_widget.setStyleSheet(f"""
            QVideoWidget {{ background-color: {COLORS['bg']};
                            border: 1px solid {COLORS['border']};
                            border-radius: 4px; }}
        """)
        layout.addWidget(self._video_widget, stretch=1)

        # Панель управления
        controls = QHBoxLayout()
        controls.setSpacing(4)

        self._btn_play = QPushButton("▶")
        self._btn_play.setFixedWidth(36)
        self._btn_play.clicked.connect(self._toggle_play)
        controls.addWidget(self._btn_play)

        self._btn_stop = QPushButton("⏹")
        self._btn_stop.setFixedWidth(36)
        self._btn_stop.clicked.connect(self._player.stop)
        controls.addWidget(self._btn_stop)

        self._pos_slider = QSlider(Qt.Horizontal)
        self._pos_slider.setRange(0, 1000)
        self._pos_slider.sliderPressed.connect(self._on_slider_pressed)
        self._pos_slider.sliderMoved.connect(self._seek)
        self._pos_slider.sliderReleased.connect(self._on_slider_released)
        controls.addWidget(self._pos_slider, stretch=1)

        self._time_label = QLabel("00:00 / 00:00")
        self._time_label.setStyleSheet(f"color: {COLORS['text2']}; font-size: 10px;")
        controls.addWidget(self._time_label)

        layout.addLayout(controls)

        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.errorOccurred.connect(self._on_error)

    # ── Публичное API ──────────────────────────────────────────────────

    def load(self, path: Path) -> None:
        """Загрузить видеофайл, сбросить обрезку на весь файл."""
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._range_start_ms = 0
        self._range_end_ms = -1
        self._time_label.setText("00:00 / 00:00")
        self._pos_slider.setValue(0)

    def unload(self) -> None:
        self._player.stop()
        self._player.setSource(QUrl())

    def set_playback_range(self, start_sec: float, end_sec: float,
                           duration: float) -> None:
        """Ограничить воспроизведение отрезком [start, end].

        Работает на любой версии PySide6 — range реализован через
        positionChanged, без QTimeRange.
        """
        self._range_start_ms = max(0, int(start_sec * 1000))
        if end_sec > 0 and end_sec < duration:
            self._range_end_ms = int(end_sec * 1000)
        else:
            self._range_end_ms = -1
        # Если плеер за границами — возвращаем на IN
        cur = self._player.position()
        if cur < self._range_start_ms or (self._range_end_ms > 0 and cur > self._range_end_ms):
            self._player.setPosition(self._range_start_ms)

    # ── Внутреннее ─────────────────────────────────────────────────────

    def _toggle_play(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _seek(self, value: int) -> None:
        dur = self._player.duration()
        if dur > 0:
            self._player.setPosition(int(value / 1000 * dur))

    def _on_slider_pressed(self) -> None:
        self._user_dragging = True

    def _on_slider_released(self) -> None:
        self._user_dragging = False
        # Применяем позицию (уже установленную через sliderMoved → _seek)
        # Просто снимаем флаг блокировки

    def _on_duration_changed(self, duration: int) -> None:
        self._pos_slider.setValue(0)

    def _on_position_changed(self, pos: int) -> None:
        if self._user_dragging:
            return

        # ── Range guard: не пускаем за OUT ──
        if self._range_end_ms > 0 and pos >= self._range_end_ms:
            self._player.stop()
            self._player.setPosition(self._range_start_ms)
            return

        dur = self._player.duration()
        if dur > 0:
            self._pos_slider.setValue(int(pos / dur * 1000))
            cur = _fmt_time2(pos / 1000)
            total = _fmt_time2(dur / 1000)
            self._time_label.setText(f"{cur} / {total}")

    def _on_state_changed(self, state):
        if state == QMediaPlayer.PlayingState:
            self._btn_play.setText("⏸")
        else:
            self._btn_play.setText("▶")

    def _on_error(self, error, error_string):
        self._time_label.setText(f"⚠ {error_string}")


def _fmt_time2(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    return f"{m:02d}:{s:02d}"


class PreviewPanel(QWidget):
    """Панель: миниатюра/видео + медиа-инфо + навигация + таймлайн.

    Сохраняет trim при переключении файлов через _trim_map.
    """

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

        # ── Навигация ──
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

        # ── Медиа-стек: 0=изо, 1=видео ──
        self._media_stack = QStackedWidget()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background-color: {COLORS['bg']};
                           border: 1px solid {COLORS['border']};
                           border-radius: 4px; }}
        """)
        self._image_label = _ScaledLabel()
        scroll.setWidget(self._image_label)
        self._media_stack.addWidget(scroll)  # 0

        self._video_player = _VideoPlayerWidget()
        self._media_stack.addWidget(self._video_player)  # 1

        layout.addWidget(self._media_stack, stretch=1)

        # ── Инфо ──
        info_frame = QFrame()
        info_frame.setFrameShape(QFrame.StyledPanel)
        info_frame.setStyleSheet(f"""
            QFrame {{ background-color: {COLORS['surface']};
                      border: 1px solid {COLORS['border']};
                      border-radius: 4px; }}
            QLabel {{ color: {COLORS['text2']}; font-size: 11px; }}
        """)
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(6, 4, 6, 4)
        info_layout.setSpacing(1)
        self._info_name = QLabel("")
        self._info_name.setStyleSheet(
            f"font-weight: bold; color: {COLORS['text']}; font-size: 12px;"
        )
        info_layout.addWidget(self._info_name)
        self._info_lines: list[QLabel] = []
        for _ in range(8):
            lbl = QLabel("")
            info_layout.addWidget(lbl)
            self._info_lines.append(lbl)
        layout.addWidget(info_frame)

        # ── Таймлайн ──
        self._timeline = TimelineWidget()
        self._timeline.trim_changed.connect(self._on_trim_changed)
        self._timeline.setVisible(False)
        layout.addWidget(self._timeline)

    # ── Публичное API ──────────────────────────────────────────────────

    @property
    def current_path(self) -> Path | None:
        return self._current_path

    def get_trim(self, path: Path) -> tuple[float, float]:
        return self._trim_map.get(path, (0.0, 0.0))

    def show(self, path: Path, idx: int, total: int,
             fmt_var: str = "", quality: int = 85,
             max_size: int = 0) -> None:
        """Показать предпросмотр. Сохраняет/восстанавливает trim из _trim_map."""
        old_path = self._current_path

        # Сохраняем trim для старого файла
        if old_path and old_path in self._trim_map:
            pass  # уже сохранён через _on_trim_changed

        self._current_path = path
        ext = path.suffix.lower()

        # Навигация
        self._nav_label.setText(f"{idx + 1} / {total}")
        self._btn_prev.setEnabled(idx > 0)
        self._btn_next.setEnabled(idx < total - 1)
        self._info_name.setText(f"📄 {path.name}")

        sym = ("🎬" if ext in VIDEO_INPUT
               else "🎵" if ext in AUDIO_INPUT
               else "🖼")
        size_str = _fmt_size(_file_size(path))
        fmt_out = resolve_format(fmt_var or "", ext)
        lines = [f"{sym}  {size_str}  →  .{fmt_out}  (q={quality})"]
        is_media = ext in (VIDEO_INPUT | AUDIO_INPUT)

        # Медиа-инфо
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
                ch = {"1": "моно", "2": "стерео", "6": "5.1", "8": "7.1"}
                if info.audio_channels:
                    parts.append(ch.get(str(info.audio_channels), f"{info.audio_channels}ch"))
                if info.sample_rate:
                    parts.append(f"{info.sample_rate // 1000}kHz")
                lines.append("  ".join(parts))
        else:
            try:
                with PILImage.open(path) as img:
                    lines.append(f"📐 {img.width}×{img.height}")
            except Exception:
                pass

        # Заполняем инфо
        for i, line in enumerate(lines):
            if i < len(self._info_lines):
                self._info_lines[i].setText(line)
        for i in range(len(lines), len(self._info_lines)):
            self._info_lines[i].setText("")

        # ── Медиа-отображение + таймлайн ──
        if ext in VIDEO_INPUT:
            self._media_stack.setCurrentIndex(1)
            self._video_player.load(path)
            self._image_label.clear_image()
            self._timeline.set_file(path)
            # Восстанавливаем trim, если был сохранён
            self._restore_trim(path)
            return

        if ext in AUDIO_INPUT:
            self._media_stack.setCurrentIndex(0)
            self._video_player.unload()
            self._image_label.clear_image()
            self._image_label.setText("🎵\n(аудио — waveform на таймлайне)")
            self._timeline.set_file(path)
            self._restore_trim(path)
            return

        # Изо
        self._media_stack.setCurrentIndex(0)
        self._video_player.unload()
        self._timeline.setVisible(False)
        try:
            with PILImage.open(path) as img:
                if img.width > 4000 or img.height > 4000:
                    img.thumbnail((4000, 4000), PILImage.LANCZOS)
                self._image_label.set_image(img)
        except Exception:
            self._image_label.clear_image()

    def clear(self) -> None:
        self._current_path = None
        self._nav_label.setText("— / —")
        self._btn_prev.setEnabled(False)
        self._btn_next.setEnabled(False)
        self._info_name.setText("(нет файла)")
        self._media_stack.setCurrentIndex(0)
        self._image_label.clear_image()
        self._video_player.unload()
        self._timeline.set_file(None)
        for lbl in self._info_lines:
            lbl.setText("")

    # ── Trim ───────────────────────────────────────────────────────────

    def _on_trim_changed(self, path: Path, start: float, end: float) -> None:
        """Сохранить trim и применить к видеоплееру."""
        self._trim_map[path] = (start, end)
        # Обновить playbackRange в плеере (если видео)
        if path == self._current_path:
            ext = path.suffix.lower()
            if ext in VIDEO_INPUT:
                info = get_media_info(path)
                self._video_player.set_playback_range(
                    start, end, info.duration or 0,
                )

    def _restore_trim(self, path: Path) -> None:
        """Восстановить trim из _trim_map после установки таймлайна."""
        saved = self._trim_map.get(path)
        if saved:
            start, end = saved
            self._timeline.set_trim_silent(start, end)
            # Применить к плееру
            ext = path.suffix.lower()
            if ext in VIDEO_INPUT:
                info = get_media_info(path)
                self._video_player.set_playback_range(
                    start, end, info.duration or 0,
                )
