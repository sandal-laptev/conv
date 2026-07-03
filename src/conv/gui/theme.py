"""Цветовая схема, шрифты и вспомогательные функции для GUI."""

from pathlib import Path

import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

COLORS = {
    "bg": "#0a0a2e",
    "surface": "#1a1a3e",
    "surface2": "#252550",
    "accent": "#00d4ff",
    "accent2": "#7b2ff7",
    "success": "#00e676",
    "error": "#ff1744",
    "text": "#e0e0e0",
    "text2": "#9e9e9e",
    "text3": "#616161",
}


def fmt_size(b: int) -> str:
    """Форматирует размер в B/KB/MB/GB."""
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.2f} TB"


def fmt_time(s: float) -> str:
    """Форматирует секунды в человекочитаемый вид."""
    if s < 60:
        return f"{s:.1f}с"
    m, r = divmod(s, 60)
    if m < 60:
        return f"{int(m)}м {r:.0f}с"
    h, m = divmod(m, 60)
    return f"{int(h)}ч {int(m)}м"


def file_size(path: Path) -> int:
    """Безопасно возвращает размер файла."""
    try:
        return path.stat().st_size
    except OSError:
        return 0
