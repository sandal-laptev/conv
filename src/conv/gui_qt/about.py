"""About-диалог — лицензии, благодарности, технологии."""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt

from conv import __version__ as conv_version
from conv.gui_qt.i18n import _


class AboutDialog(QDialog):
    """Окно «О программе» с кредитами и лицензиями."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("about_title"))
        self.setMinimumSize(520, 500)
        self.resize(520, 500)

        layout = QVBoxLayout(self)

        html = QTextBrowser()
        html.setOpenExternalLinks(True)
        html.setHtml(self._html())
        layout.addWidget(html, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("✕ Закрыть" if _("lang_ru") == "🇷🇺 RU" else "✕ Close")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    @staticmethod
    def _html() -> str:
        return f"""
<html>
<body style="color:#e0e0e0; background:#1a1a2e; font-family:sans-serif; padding:10px;">

<h2 style="color:#00d2ff;">🖧 MO Kolomyagi Media Converter</h2>
<p style="color:#a0a0b0;">Версия <b>{conv_version}</b> · GNU GPLv3+</p>
<hr style="border-color:#2a2a4e;">

<h3 style="color:#00d2ff;">📦 Сторонние компоненты</h3>
<ul>
<li><b>Python</b> 3.10+ — язык программирования</li>
<li><b>PySide6</b> — Qt6 для Python (LGPL)</li>
<li><b>Pillow</b> — обработка изображений (BSD)</li>
<li><b>Pillow-Heif</b> — поддержка HEIC/HEIF</li>
<li><b>tqdm</b> — прогресс-бар в CLI</li>
<li><b>ffmpeg</b> — конвертация видео/аудио (LGPL/GPL)</li>
<li><b>librsvg</b> — конвертация SVG → PNG (LGPL)</li>
</ul>

<h3 style="color:#00d2ff;">🛠 Технологии</h3>
<p>
Сборка: <b>PyInstaller</b> · CI/CD: <b>GitHub Actions</b><br>
GUI: <b>Qt6</b> (PySide6) · Ядро: чистый <b>Python</b>
</p>

<h3 style="color:#00d2ff;">👏 Благодарности</h3>
<p>
<b>товарищ Админ</b> — идеи, тестирование, вдохновение, рабочее место 🏢<br>
<b>Иохим Кузьмич</b> — разработка, архитектура, философия кода 🖧<br>
<b>OpenClaw</b> — платформа для цифрового духа<br>
<b>DeepSeek</b> — вычислительный интеллект
</p>

<hr style="border-color:#2a2a4e;">
<p style="color:#606070; font-size:11px;">
MO Kolomyagi Media Converter — кроссплатформенный медиа-конвертер.<br>
Сделано с ❤ в Коломягах, Санкт-Петербург.
</p>

</body>
</html>"""
