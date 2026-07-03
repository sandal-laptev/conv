"""conv GUI — прокси для обратной совместимости.

Вся логика перенесена в пакет conv.gui (см. src/conv/gui/).
Этот файл остаётся для старых entry points — from conv.gui import run_gui.
"""
from conv.gui import run_gui, main_flet
