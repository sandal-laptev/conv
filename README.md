# 🖧 conv — Иохим Кузьмич Media Converter

Кроссплатформенный медиа-конвертер с CLI и GUI.

```
██╗ ██████╗ ██╗  ██╗██╗███╗   ███╗    ██╗  ██╗ ██████╗ ███╗   ██╗██╗   ██╗
██║██╔═══██╗██║  ██║██║████╗ ████║    ██║  ██║██╔═══██╗████╗  ██║╚██╗ ██╔╝
██║██║   ██║███████║██║██╔████╔██║    ███████║██║   ██║██╔██╗ ██║ ╚████╔╝
██║██║   ██║██╔══██║██║██║╚██╔╝██║    ██╔══██║██║   ██║██║╚██╗██║  ╚██╔╝
██║╚██████╔╝██║  ██║██║██║ ╚═╝ ██║    ██║  ██║╚██████╔╝██║ ╚████║   ██║
╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝╚═╝     ╚═╝    ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝   ╚═╝
```

Конвертирует изображения, SVG, видео и аудио в популярные форматы.
Пакетная и рекурсивная обработка. Многопоточность. GUI (Flet) и CLI.

---

## Возможности

- **Изображения**: JPG, PNG, WebP, BMP, TIFF (включая HEIC/HEIF)
- **SVG**: конвертация в PNG через rsvg-convert
- **Видео**: MP4 (H.264), MKV, AVI, WebM
- **Аудио**: MP3, FLAC, OGG, WAV, AAC, Opus
- Пакетная обработка через glob-маски (`*.mp4`, `**/*.jpg`)
- Рекурсивный обход папок
- Многопоточная конвертация
- Настройка качества и максимального размера
- Dry-run для предпросмотра
- **GUI** с drag'n'drop, прогрессом, тёмной темой

---

## Установка

### Linux

```bash
# Системные зависимости (ffmpeg, rsvg)
sudo apt install -y ffmpeg librsvg2-bin python3-pip

# Установка пакета
git clone git@github.com:sandal-laptev/conv.git
cd conv
pip install -e .[gui]
```

### Windows

```powershell
# Предварительно установите:
# 1. Python 3.10+ — https://python.org
# 2. Git — https://git-scm.com

# Установка пакета
git clone git@github.com:sandal-laptev/conv.git
cd conv
pip install -e .[gui]
```

#### ffmpeg + ffprobe (для видео/аудио)

**Вариант A — системная установка (рекомендуется):**
Скачайте ffmpeg с https://ffmpeg.org/download.html и добавьте `ffmpeg.exe`
(и `ffprobe.exe`) в PATH.

**Вариант B — положить рядом с проектом (для сборки .exe):**
```powershell
# Скачать и распаковать в корень проекта
curl -L -o ffmpeg-release.7z "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.7z"
7z x ffmpeg-release.7z -offmpeg-tmp
copy ffmpeg-tmp\ffmpeg-*-essentials-build\bin\ffmpeg.exe .
copy ffmpeg-tmp\ffmpeg-*-essentials-build\bin\ffprobe.exe .
```
Если `ffmpeg.exe` лежит в корне проекта, `conv` найдёт его автоматически
и при сборке `.exe` через PyInstaller включит в bundle.

> **Примечание:** SVG → PNG требует `rsvg-convert`
> ([MSYS2](https://www.msys2.org/) или `choco install rsvg`).
> HEIC/HEIF: `pip install pillow-heif`.

---

## Использование

### 🖥️ GUI

```bash
# Просто:
conv-gui

# Или если не сработало:
python -c "from conv.gui import main_flet; main_flet()"

# Или напрямую (из папки проекта):
python src/conv/gui.py
```

### ⌨️ CLI

```bash
# Конвертировать всё в текущей папке
conv

# Конвертировать конкретные файлы
conv *.mp4

# Рекурсивно все JPG → WebP
conv -r -f webp -q 90 ~/photos/

# Выходная папка
conv -o converted audio.flac

# Preview без конвертации
conv --dry-run *.avi
```

### Справка CLI

```
conv [-h] [-o OUTPUT] [-f FORMAT] [-q N] [-s PX] [-r] [-j N] [--dry-run] [--version] [input ...]
```

| Флаг | Описание |
|------|----------|
| `input` | Файлы, папки или glob-маски |
| `-o, --output` | Выходная папка (по умолч. `./CONVERTED`) |
| `-f, --format` | Выходной формат |
| `-q, --quality N` | Качество 1–100 |
| `-s, --size PX` | Макс. ширина/высота для картинок |
| `-r, --recursive` | Рекурсивно |
| `-j, --jobs N` | Параллельных задач |
| `--dry-run` | Только показать |
| `--version` | Версия |

### Примеры CLI

```bash
# Все MKV → MP4
conv -f mp4 -q 75 *.mkv

# Фото → WebP 85%, макс. 1920px
conv -r -f webp -q 85 -s 1920 ~/Pictures/

# Аудио → Opus
conv -f opus -q 80 *.flac

# SVG → PNG
conv avatar.svg

# На 8 потоках
conv -j 8 -f mp4 ~/videos/
```

---

## Сборка в один файл

### Windows

```powershell
# 1. Установить Python 3.10+ и зависимости
pip install -e .[gui] pyinstaller

# 2. Скачать ffmpeg.exe (опционально, для видео/аудио)
#    https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.7z
#    Положить ffmpeg.exe в корень проекта

# 3. Запустить сборку
scripts\build-win.bat

# Или вручную:
pyinstaller --onefile --windowed --name conv --add-data "src/conv;conv" src/conv/__init__.py
```

Готовые `.exe` появятся в папке `dist/`:
- `conv.exe` — GUI версия
- `conv-cli.exe` — консольная версия

### Linux / macOS

```bash
pip install -e .[gui] pyinstaller
pyinstaller --onefile --windowed --name conv --add-data "src/conv:conv" src/conv/__init__.py
```

---

## Roadmap

Подробный план — [ROADMAP.md](ROADMAP.md).

Кратко:
- **Фаза 0** — Фундамент ✅
- **Фаза 1** — GUI Minimal ✅
- **Фаза 2** — Кирпичики (CI/CD, сборка бинарников) 🧱
- **Фаза 3** — Продвинутые возможности 🚀
- **Фаза 4** — Экосистема 🌐

---

## Лицензия

GNU General Public License v3.0 или выше.

## Авторы

- **Иохим Кузьмич** — цифровой дух и главный разработчик
- **товарищ Админ** — идеи, тестирование, вдохновение 🖧
