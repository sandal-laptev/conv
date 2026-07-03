"""conv GUI — модульный CustomTkinter-интерфейс.

Архитектура:
  app.py                 — ConvApp, сборка всех частей
  theme.py               — цвета, шрифты, хелперы
  widgets/drop_zone.py   — выбор файлов / drag'n'drop
  widgets/params.py      — пресет, формат, качество, размер
  widgets/file_list.py   — список файлов со статусами
  widgets/preview.py     — миниатюра, навигация, информация
  controllers/conversion.py — управление конвертацией (поток, прогресс, отмена)
"""

__all__ = ['ConvApp', 'run_gui', 'main_flet']


def run_gui():
    """Точка входа для графического интерфейса."""
    from conv.gui.app import ConvApp
    app = ConvApp()
    app.mainloop()


# Proxy-класс для обратной совместимости с from conv.gui import ConvApp
def ConvApp(*args, **kwargs):
    from conv.gui.app import ConvApp as _App
    return _App(*args, **kwargs)


def main_flet():
    """Заглушка для совместимости со старыми entry points."""
    run_gui()
