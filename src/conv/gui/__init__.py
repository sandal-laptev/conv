"""Qt6 GUI для conv — запуск через `python -m conv.gui`."""


def run_gui() -> None:
    """Запустить Qt-версию графического интерфейса."""
    import sys
    from PySide6.QtWidgets import QApplication
    from conv.gui.app import ConvApp
    from conv.gui.theme import apply_dark_theme

    app = QApplication(sys.argv)
    apply_dark_theme(app)

    window = ConvApp()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    run_gui()
