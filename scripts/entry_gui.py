"""Точка входа для PyInstaller (GUI)."""
import sys
import os

# Убедимся, что папка с bundled-ресурсами в пути
if getattr(sys, 'frozen', False):
    os.environ['PATH'] = sys._MEIPASS + os.pathsep + os.environ.get('PATH', '')

# Принудительный импорт pillow_heif — чтобы PyInstaller всегда подхватывал
try:
    from pillow_heif import register_heif_opener  # noqa
    register_heif_opener()
except Exception:
    pass

from conv.gui import run_gui
run_gui()
