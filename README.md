# 🖧 MO Kolomyagi Media Converter

Кроссплатформенный медиа-конвертер с CLI и Qt6 GUI.

```
██╗ ██████╗ ██╗  ██╗██╗███╗   ███╗    ██╗  ██╗ ██████╗ ███╗   ██╗██╗   ██╗
██║██╔═══██╗██║  ██║██║████╗ ████║    ██║  ██║██╔═══██╗████╗  ██║╚██╗ ██╔╝
██║██║   ██║███████║██║██╔████╔██║    ███████║██║   ██║██╔██╗ ██║ ╚████╔╝
██║██║   ██║██╔══██║██║██║╚██╔╝██║    ██╔══██║██║   ██║██║╚██╗██║  ╚██╔╝
██║╚██████╔╝██║  ██║██║██║ ╚═╝ ██║    ██║  ██║╚██████╔╝██║ ╚████║   ██║
╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝╚═╝     ╚═╝    ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝   ╚═╝
```

Конвертирует изображения, SVG, видео и аудио в популярные форматы.
Пакетная и рекурсивная обработка. Многопоточность. **Qt6 GUI** и **CLI**.

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
- **Пресеты качества**: Макс., Для веба, Быстрый
- Dry-run для предпросмотра
- **🚀 Qt6 GUI**:
  - Drag'n'drop файлов и папок из Проводника
  - Тёмная / светлая / системная тема
  - 🎬 **Видеоплеер** с обрезкой IN/OUT (без перекодирования)
  - 📊 **Таймлайн** с waveform, range-drag, ручной ввод времени
  - 🖼 **Предпросмотр изображений** (PIL → QPixmap)
  - 🌐 **RU / EN** переключение языка
  - ☑️ Чекбоксы, контекстное меню, горячие клавиши
  - 📁 **Сортировка по типу** (images / video / audio)
  - 💾 Память настроек между запусками (ConfigManager)
  - ℹ About-диалог с лицензиями и благодарностями

---

## Установка

### Linux

```bash
# Системные зависимости (ffmpeg, rsvg)
sudo apt install -y ffmpeg librsvg2-bin python3-pip

# Установка пакета
git clone git@github.com:sandal-laptev/conv.git
cd conv
pip install -e .[gui,heif]
```

### Windows

```powershell
# Предварительно установите:
# 1. Python 3.10+ — https://python.org
# 2. Git — https://git-scm.com

# Установка пакета
git clone git@github.com:sandal-laptev/conv.git
cd conv
pip install -e .[gui,heif]
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
# Qt6 GUI (рекомендуется)
conv-gui

# Или напрямую:
python -m conv.gui
```

#### Горячие клавиши (GUI)

| Клавиша | Действие |
|---------|----------|
| `Ctrl+A` / `Ctrl+Shift+A` | ✅ Всё / ❌ Снять |
| `Ctrl+I` | 🔀 Инвертировать |
| `Delete` | 🗑 Удалить файл |
| `Enter` | ⚡ Конвертировать |
| `Ctrl+O` / `Ctrl+Shift+O` | 📂 Файлы / 📁 Папка |
| `Ctrl+.` | 📂 Открыть папку |
| `Space` | ▶⏸ Play/Pause видео |
| `Esc` | ⏹ Отмена / 🗑 Очистить |

### ⌨️ CLI

```bash
# Конвертировать всё в текущей папке
conv

# Конвертировать конкретные файлы
conv *.mp4

# Рекурсивно все JPG → WebP
conv -r -f webp -q 90 ~/photos/

# Выходная папка + сортировка по типу
conv -o converted --sort-by-type audio.flac

# Preview без конвертации
conv --dry-run *.avi
```

### Справка CLI

```
conv [-h] [-o OUTPUT] [-f FORMAT] [-q N] [-s PX] [-r] [-j N]
     [--preset PRESET] [--sort-by-type] [--rename-to EXT]
     [--trim-start S] [--trim-end S] [--info] [--dry-run]
     [--version] [input ...]
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
| `--preset` | Пресет качества (max / web / fast) |
| `--sort-by-type` | Сортировать по типу (video/audio/image) |
| `--rename-to` | Переименовать (без перекодирования) |
| `--trim-start/--trim-end` | Обрезка видео/аудио (сек) |
| `--info` | Медиа-информация |
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

# Обрезка: первые 30 секунд
conv --trim-end 30 clip.mp4

# С сортировкой по типу
conv -o converted --sort-by-type *.mp4 *.jpg *.flac
```

---

## Сборка в один .exe (Windows)

```powershell
# 1. Установить Python 3.10+ и зависимости
pip install -e .[gui,heif] pyinstaller

# 2. Скачать ffmpeg.exe (опционально, для видео/аудио)
#    https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.7z
#    Положить ffmpeg.exe в корень проекта

# 3. Запустить сборку
scripts\build-win.bat
```

Готовые `.exe` появятся в папке `dist/`:
- `MO-Kolomyagi-Media-Converter.exe` — Qt6 GUI (∼150–350 MB)
- `conv-cli.exe` — консольная версия

> **Примечание:** Большой размер .exe обусловлен встроенным Qt6
> (PySide6 + Qt Multimedia). Это плата за видеоплеер, таймлайн
> и нативную кроссплатформенность.

---

## Roadmap

Подробный план — [ROADMAP.md](ROADMAP.md).

Кратко:
- **Фаза 0** — Фундамент ✅
- **Фаза 1** — CLI + ядро ✅
- **Фаза 2** — CI/CD, сборка бинарников ✅
- **Фаза 3** — Qt6 GUI (видеоплеер, таймлайн, i18n, темы) 🚀
- **В плане** — Автоопределение формата

---

## Лицензия

GNU General Public License v3.0 или выше.

## Авторы

- **Иохим Кузьмич** — цифровой дух, архитектор, главный разработчик 🖧
- **товарищ Админ** — идеи, тестирование, вдохновение, рабочее место 🏢

Сделано с ❤ в Коломягах, Санкт-Петербург.

---

*Powered by OpenClaw · DeepSeek*
