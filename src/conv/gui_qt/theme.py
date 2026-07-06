"""Темы оформления — тёмная, светлая, системная."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

COLORS_DARK = {
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

COLORS_LIGHT = {
    "bg": "#f5f5f5",
    "surface": "#ffffff",
    "surface2": "#e8e8e8",
    "accent": "#0078d4",
    "text": "#1a1a1a",
    "text2": "#505050",
    "text3": "#909090",
    "error": "#d32f2f",
    "success": "#2e7d32",
    "border": "#cccccc",
    "header_bg": "#e0e0e0",
}

COLORS = COLORS_DARK  # дефолт, будет заменён


def apply_dark_theme(app: QApplication) -> None:
    """Тёмная тема."""
    global COLORS
    COLORS = COLORS_DARK
    _apply_palette(app, COLORS_DARK)


def apply_light_theme(app: QApplication) -> None:
    """Светлая тема."""
    global COLORS
    COLORS = COLORS_LIGHT
    _apply_palette(app, COLORS_LIGHT)


def apply_system_theme(app: QApplication) -> None:
    """Системная тема (Fusion по умолчанию, переопределяем через палитру)."""
    global COLORS
    COLORS = COLORS_DARK
    # Системная = используем системную палитру Qt
    app.setStyle("Fusion")
    app.setPalette(app.style().standardPalette())
    app.setStyleSheet("")


def _apply_palette(app: QApplication, c: dict) -> None:
    app.setStyle("Fusion")
    palette = QPalette()

    palette.setColor(QPalette.Window, QColor(c["bg"]))
    palette.setColor(QPalette.WindowText, QColor(c["text"]))
    palette.setColor(QPalette.Base, QColor(c["surface"]))
    palette.setColor(QPalette.AlternateBase, QColor(c["surface2"]))
    palette.setColor(QPalette.ToolTipBase, QColor(c["surface2"]))
    palette.setColor(QPalette.ToolTipText, QColor(c["text"]))
    palette.setColor(QPalette.Text, QColor(c["text"]))
    palette.setColor(QPalette.Button, QColor(c["surface"]))
    palette.setColor(QPalette.ButtonText, QColor(c["text"]))
    palette.setColor(QPalette.BrightText, QColor(c["accent"]))
    palette.setColor(QPalette.Link, QColor(c["accent"]))
    palette.setColor(QPalette.Highlight, QColor(c["accent"]))
    palette.setColor(QPalette.HighlightedText, QColor(c["bg"]))

    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor(c["text3"]))

    app.setPalette(palette)

    app.setStyleSheet(_qss(c))


def _qss(c: dict) -> str:
    return f"""
        QToolTip {{
            color: {c["text"]}; background-color: {c["surface2"]};
            border: 1px solid {c["border"]}; padding: 4px;
        }}
        QMenu {{
            background-color: {c["surface"]}; color: {c["text"]};
            border: 1px solid {c["border"]};
        }}
        QMenu::item:selected {{
            background-color: {c["accent"]}; color: {c["bg"]};
        }}
        QHeaderView::section {{
            background-color: {c["header_bg"]}; color: {c["text2"]};
            padding: 4px 8px; border: none;
            border-right: 1px solid {c["border"]};
            border-bottom: 1px solid {c["border"]};
            font-weight: bold;
        }}
        QTableView, QTreeView {{
            gridline-color: {c["border"]};
            border: 1px solid {c["border"]}; border-radius: 4px;
            alternate-background-color: {c["surface"]};
        }}
        QTableView::item, QTreeView::item {{ padding: 2px 4px; }}
        QTableView::item:selected, QTreeView::item:selected {{
            background-color: {c["accent"]}; color: {c["bg"]};
        }}
        QProgressBar {{
            background-color: {c["surface"]};
            border: 1px solid {c["border"]}; border-radius: 4px;
            text-align: center; color: {c["text2"]}; height: 20px;
        }}
        QProgressBar::chunk {{
            background-color: {c["accent"]}; border-radius: 3px;
        }}
        QPushButton {{
            padding: 4px 12px; border: 1px solid {c["border"]};
            border-radius: 4px; background-color: {c["surface"]};
            color: {c["text"]};
        }}
        QPushButton:hover {{
            background-color: {c["surface2"]}; border-color: {c["accent"]};
        }}
        QPushButton:pressed {{
            background-color: {c["accent"]}; color: {c["bg"]};
        }}
        QPushButton:disabled {{ color: {c["text3"]}; border-color: {c["border"]}; }}
        QComboBox {{
            padding: 2px 8px; border: 1px solid {c["border"]};
            border-radius: 4px; background-color: {c["surface"]};
            color: {c["text"]};
        }}
        QComboBox:hover {{ border-color: {c["accent"]}; }}
        QComboBox::drop-down {{ border: none; width: 20px; }}
        QComboBox QAbstractItemView {{
            background-color: {c["surface"]}; color: {c["text"]};
            selection-background-color: {c["accent"]}; selection-color: {c["bg"]};
        }}
        QLineEdit {{
            padding: 2px 6px; border: 1px solid {c["border"]};
            border-radius: 4px; background-color: {c["surface"]};
            color: {c["text"]};
        }}
        QLineEdit:focus {{ border-color: {c["accent"]}; }}
        QCheckBox {{ color: {c["text"]}; }}
        QCheckBox::indicator {{
            width: 14px; height: 14px; border: 1px solid {c["border"]};
            border-radius: 3px; background-color: {c["surface"]};
        }}
        QCheckBox::indicator:checked {{
            background-color: {c["accent"]}; border-color: {c["accent"]};
        }}
        QSlider::groove:horizontal {{
            height: 6px; background: {c["surface"]}; border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background: {c["accent"]}; width: 14px; height: 14px;
            margin: -4px 0; border-radius: 7px;
        }}
        QSlider::sub-page:horizontal {{
            background: {c["accent"]}; border-radius: 3px;
        }}
        QScrollBar:vertical {{
            background: {c["bg"]}; width: 10px; border: none;
        }}
        QScrollBar::handle:vertical {{
            background: {c["surface2"]}; border-radius: 5px; min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {c["accent"]}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """
