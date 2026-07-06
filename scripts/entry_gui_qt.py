"""Точка входа для PyInstaller (Qt6 GUI)."""
import sys
import os

# Убедимся, что bundled-ресурсы в пути
if getattr(sys, 'frozen', False):
    os.environ['PATH'] = sys._MEIPASS + os.pathsep + os.environ.get('PATH', '')

# Принудительный импорт pillow_heif — чтобы PyInstaller подхватывал
try:
    from pillow_heif import register_heif_opener  # noqa
    register_heif_opener()
except Exception:
    pass

from conv.gui_qt import run_gui
run_gui()
