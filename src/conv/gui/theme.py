"""Цветовая схема, шрифты и вспомогательные функции для GUI."""

import re
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


# ── Парсинг / формат времени (для обрезки) ────────────────────────────

_TIME_RE = re.compile(
    r"^(?:(\d+):)?(\d+):([\d.]+)$"   # HH:MM:SS.mmm | MM:SS.mmm
)
_FLOAT_RE = re.compile(r"^[\d.]+$")


def parse_time(text: str) -> float:
    """Парсит время из строки: секунды, MM:SS или HH:MM:SS."""
    text = text.strip()
    if not text:
        return 0.0
    m = _TIME_RE.match(text)
    if m:
        h = int(m.group(1) or 0)
        mm = int(m.group(2))
        s = float(m.group(3))
        return h * 3600 + mm * 60 + s
    if _FLOAT_RE.match(text):
        return float(text)
    return 0.0


def fmt_trim(seconds: float) -> str:
    """Форматирует секунды в MM:SS или HH:MM:SS."""
    if seconds <= 0:
        return "—"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:05.2f}"
    return f"{m}:{s:05.2f}"
