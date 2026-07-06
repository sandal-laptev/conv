"""Тёмная тема для PySide6 — QPalette + QSS."""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

COLORS = {
    "bg": "#1a1a2e",
    "surface": "#16213e",
    "surface2": "#0f3460",
    "accent": "#00d2ff",
    "text": "#e0e0e0",
    "text2": "#a0a0b0",
    "text3": "#606070",
    "error": "#ff4444",
    "success": "#44cc44",
    "border": "#2a2a4e",
    "header_bg": "#12122a",
}


def apply_dark_theme(app: QApplication) -> None:
    """Применить тёмную палитру и QSS ко всему приложению."""
    app.setStyle("Fusion")

    palette = QPalette()

    # Основные цвета
    palette.setColor(QPalette.Window, QColor(COLORS["bg"]))
    palette.setColor(QPalette.WindowText, QColor(COLORS["text"]))
    palette.setColor(QPalette.Base, QColor(COLORS["surface"]))
    palette.setColor(QPalette.AlternateBase, QColor(COLORS["surface2"]))
    palette.setColor(QPalette.ToolTipBase, QColor(COLORS["surface2"]))
    palette.setColor(QPalette.ToolTipText, QColor(COLORS["text"]))
    palette.setColor(QPalette.Text, QColor(COLORS["text"]))
    palette.setColor(QPalette.Button, QColor(COLORS["surface"]))
    palette.setColor(QPalette.ButtonText, QColor(COLORS["text"]))
    palette.setColor(QPalette.BrightText, QColor(COLORS["accent"]))
    palette.setColor(QPalette.Link, QColor(COLORS["accent"]))
    palette.setColor(QPalette.Highlight, QColor(COLORS["accent"]))
    palette.setColor(QPalette.HighlightedText, QColor(COLORS["bg"]))

    # Disabled
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor(COLORS["text3"]))

    app.setPalette(palette)

    # Дополнительный QSS для тонкой настройки
    app.setStyleSheet(f"""
        QToolTip {{
            color: {COLORS["text"]};
            background-color: {COLORS["surface2"]};
            border: 1px solid {COLORS["border"]};
            padding: 4px;
        }}
        QMenu {{
            background-color: {COLORS["surface"]};
            color: {COLORS["text"]};
            border: 1px solid {COLORS["border"]};
        }}
        QMenu::item:selected {{
            background-color: {COLORS["accent"]};
            color: {COLORS["bg"]};
        }}
        QHeaderView::section {{
            background-color: {COLORS["header_bg"]};
            color: {COLORS["text2"]};
            padding: 4px 8px;
            border: none;
            border-right: 1px solid {COLORS["border"]};
            border-bottom: 1px solid {COLORS["border"]};
            font-weight: bold;
        }}
        QTableView, QTreeView {{
            gridline-color: {COLORS["border"]};
            border: 1px solid {COLORS["border"]};
            border-radius: 4px;
            alternate-background-color: {COLORS["surface"]};
        }}
        QTableView::item, QTreeView::item {{
            padding: 2px 4px;
        }}
        QTableView::item:selected, QTreeView::item:selected {{
            background-color: {COLORS["accent"]};
            color: {COLORS["bg"]};
        }}
        QProgressBar {{
            background-color: {COLORS["surface"]};
            border: 1px solid {COLORS["border"]};
            border-radius: 4px;
            text-align: center;
            color: {COLORS["text2"]};
            height: 20px;
        }}
        QProgressBar::chunk {{
            background-color: {COLORS["accent"]};
            border-radius: 3px;
        }}
        QPushButton {{
            padding: 4px 12px;
            border: 1px solid {COLORS["border"]};
            border-radius: 4px;
            background-color: {COLORS["surface"]};
            color: {COLORS["text"]};
        }}
        QPushButton:hover {{
            background-color: {COLORS["surface2"]};
            border-color: {COLORS["accent"]};
        }}
        QPushButton:pressed {{
            background-color: {COLORS["accent"]};
            color: {COLORS["bg"]};
        }}
        QPushButton:disabled {{
            color: {COLORS["text3"]};
            border-color: {COLORS["border"]};
        }}
        QComboBox {{
            padding: 2px 8px;
            border: 1px solid {COLORS["border"]};
            border-radius: 4px;
            background-color: {COLORS["surface"]};
            color: {COLORS["text"]};
        }}
        QComboBox:hover {{
            border-color: {COLORS["accent"]};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 20px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {COLORS["surface"]};
            color: {COLORS["text"]};
            selection-background-color: {COLORS["accent"]};
            selection-color: {COLORS["bg"]};
        }}
        QLineEdit {{
            padding: 2px 6px;
            border: 1px solid {COLORS["border"]};
            border-radius: 4px;
            background-color: {COLORS["surface"]};
            color: {COLORS["text"]};
        }}
        QLineEdit:focus {{
            border-color: {COLORS["accent"]};
        }}
        QCheckBox {{
            color: {COLORS["text"]};
        }}
        QCheckBox::indicator {{
            width: 14px;
            height: 14px;
            border: 1px solid {COLORS["border"]};
            border-radius: 3px;
            background-color: {COLORS["surface"]};
        }}
        QCheckBox::indicator:checked {{
            background-color: {COLORS["accent"]};
            border-color: {COLORS["accent"]};
        }}
        QSlider::groove:horizontal {{
            height: 6px;
            background: {COLORS["surface"]};
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background: {COLORS["accent"]};
            width: 14px;
            height: 14px;
            margin: -4px 0;
            border-radius: 7px;
        }}
        QSlider::sub-page:horizontal {{
            background: {COLORS["accent"]};
            border-radius: 3px;
        }}
        QScrollBar:vertical {{
            background: {COLORS["bg"]};
            width: 10px;
            border: none;
        }}
        QScrollBar::handle:vertical {{
            background: {COLORS["surface2"]};
            border-radius: 5px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {COLORS["accent"]};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
    """)
