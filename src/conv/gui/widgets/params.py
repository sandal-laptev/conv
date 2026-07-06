"""Панель параметров конвертации (формат, качество, размер, пресет)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from conv.core import OUTPUT_FORMATS, QUALITY_PRESETS
from conv.gui.theme import COLORS


class ParamsWidget(QWidget):
    """Настройки конвертации: пресет, формат, качество, макс. размер."""

    format_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._on_preset_change(self._preset_combo.currentText())

    # ── Публичное API ──────────────────────────────────────────────────

    @property
    def format_name(self) -> str:
        raw = self._fmt_combo.currentText()
        return "" if raw == "Авто" else raw.split(" — ")[0]

    @property
    def quality(self) -> int:
        return self._quality_slider.value()

    @property
    def max_size(self) -> int:
        try:
            return int(self._size_entry.text() or "0")
        except ValueError:
            return 0

    @property
    def sort_by_type(self) -> bool:
        return self._sort_check.isChecked()

    @sort_by_type.setter
    def sort_by_type(self, value: bool) -> None:
        self._sort_check.setChecked(value)

    @property
    def rename_only(self) -> bool:
        return self._rename_check.isChecked()

    # ── Построение ─────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Верхний ряд: пресет | формат | качество
        row1 = QHBoxLayout()
        row1.setSpacing(12)

        # Пресет
        row1.addWidget(QLabel("Пресет:"))
        self._preset_combo = QComboBox()
        self._preset_combo.setMinimumWidth(300)
        for p in QUALITY_PRESETS.values():
            self._preset_combo.addItem(f"{p.label} — {p.description}", p.name)
        self._preset_combo.addItem("— Кастом")
        self._preset_combo.currentIndexChanged.connect(
            lambda: self._on_preset_change(self._preset_combo.currentText())
        )
        row1.addWidget(self._preset_combo)

        # Формат
        row1.addSpacing(8)
        row1.addWidget(QLabel("Формат:"))
        self._fmt_combo = QComboBox()
        self._fmt_combo.setMinimumWidth(150)
        self._fmt_combo.addItem("Авто")
        for k, v in OUTPUT_FORMATS.items():
            self._fmt_combo.addItem(f"{k} — {v['desc']}")
        self._fmt_combo.currentIndexChanged.connect(self.format_changed.emit)
        row1.addWidget(self._fmt_combo)

        # Качество
        row1.addSpacing(8)
        row1.addWidget(QLabel("Качество:"))
        self._quality_slider = QSlider(Qt.Horizontal)
        self._quality_slider.setRange(1, 100)
        self._quality_slider.setValue(80)
        self._quality_slider.setFixedWidth(160)
        self._quality_label = QLabel("80%")
        self._quality_label.setStyleSheet(f"color: {COLORS['accent']};")
        self._quality_slider.valueChanged.connect(
            lambda v: self._quality_label.setText(f"{v}%")
        )
        self._quality_slider.valueChanged.connect(self._unset_preset)
        row1.addWidget(self._quality_slider)
        row1.addWidget(self._quality_label)
        row1.addStretch()

        layout.addLayout(row1)

        # Второй ряд: макс. размер + чекбоксы
        row2 = QHBoxLayout()
        row2.setSpacing(12)

        row2.addWidget(QLabel("Макс. px (0 = ориг):"))
        self._size_entry = QLineEdit()
        self._size_entry.setFixedWidth(100)
        self._size_entry.setText("1920")
        self._size_entry.textChanged.connect(self._unset_preset)
        row2.addWidget(self._size_entry)

        row2.addSpacing(16)

        self._sort_check = QCheckBox("📁 Сортировать по типу (image/video/audio)")
        row2.addWidget(self._sort_check)

        self._rename_check = QCheckBox("🔄 Только переименовать (без конвертации)")
        row2.addWidget(self._rename_check)

        row2.addStretch()
        layout.addLayout(row2)

    # ── Внутреннее ─────────────────────────────────────────────────────

    def _on_preset_change(self, choice: str):
        for p in QUALITY_PRESETS.values():
            if choice.startswith(f"{p.label} — "):
                self._quality_slider.setValue(p.quality)
                self._size_entry.setText(str(p.max_size))
                return

    def _unset_preset(self, *_):
        """Сбросить пресет при ручном изменении качества/размера."""
        idx = self._preset_combo.count() - 1  # — Кастом
        self._preset_combo.blockSignals(True)
        self._preset_combo.setCurrentIndex(idx)
        self._preset_combo.blockSignals(False)
