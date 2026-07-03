"""Точка входа для PyInstaller (GUI)."""
import sys
import os

# Убедимся, что папка с bundled-ресурсами в пути
if getattr(sys, 'frozen', False):
    os.environ['PATH'] = sys._MEIPASS + os.pathsep + os.environ.get('PATH', '')

from conv.gui import run_gui
run_gui()
