# 🗺️ ROADMAP — conv media converter

## Легенда

| Символ | Значение |
|--------|----------|
| ✅ | Готово |
| 🔧 | В работе |
| 📋 | Запланировано |
| 💡 | Идея |
| ❌ | Отложено / заменено |

---

## Фаза 0: Фундамент ✅

- [x] Выделение ядра `core.py` с чистым API
- [x] CLI-интерфейс (argparse, glob, рекурсия, многопоточность)
- [x] pyproject.toml + setup.cfg — современная сборка
- [x] GPLv3 лицензия
- [x] GitHub-репозиторий
- [x] README с примерами
- [x] ROADMAP

## Фаза 1: GUI (Tkinter) ❌

Заменён на Qt6. Tkinter-реализация удалена.
Исторически были: ~~Flet~~ → CustomTkinter → **Qt6 (PySide6)**

## Фаза 2: Кирпичики 🧱

### Ближайшее (есть запрос)

- [x] **GitHub Actions CI** — тесты на Python 3.10–3.12 при каждом пуше
- [x] **Сборка в один .exe** — PyInstaller под Windows
- [x] **GitHub Actions Release** — автоматическая сборка Win/Mac/Linux (тег v*)
- [x] **Пресеты качества** — "Макс.", "Для веба", "Быстрый"
- [x] **Проверка инструментов** — сообщать если ffmpeg/rsvg не установлены

### Следом

- [x] **Авто-определение выходного формата** по типу файла (визуально в GUI)
- [x] **Доработка CLI** — автодополнение для bash/zsh (--completion)
- [x] **man-страница** — troff + --man + data_files
- [❌] **Tkinter GUI** — заменён на Qt6 (PySide6)

## Фаза 3: Qt6 GUI — MO Kolomyagi Media Converter 🖧

### Фундамент ✅
- [x] Тёмная / светлая / системная тема (QPalette + QSS)
- [x] Параметры: формат, качество, размер, пресет
- [x] **Сортировка по типу** (image/video/audio) — ConfigManager
- [x] **Выбор выходной папки** + память между запусками
- [x] Таблица файлов (QTreeView, чекбоксы, сортировка)
- [x] Конвертация в QThread (не вешает GUI)
- [x] Прогресс-бар, ETA, статистика
- [x] `pip install conv[gui]` + `conv-gui` entry point

### Preview + Timeline ✅
- [x] Preview-панель: миниатюра (PIL→QPixmap), медиа-инфо, навигация
- [x] **Таймлайн обрезки** — два маркера IN/OUT, range-drag, waveform
- [x] **Видеоплеер** — QMediaPlayer + QVideoWidget
- [x] Playback range: слайдер и воспроизведение привязаны к IN/OUT
- [x] Ручной ввод времени MM:SS.mmm
- [x] Trim сохраняется при листании файлов

### Выбор + Drag'n'drop ✅
- [x] **Чекбоксы** — отметка файлов, контекстное меню
- [x] **Drag'n'drop** — перетаскивание файлов/папок из Проводника
- [x] Конвертация только выделенных файлов

### Горячие клавиши ✅
- [x] **Ctrl+A** / **Ctrl+Shift+A** / **Ctrl+I** — выделение
- [x] **Delete** — удалить, **Enter** — конвертировать
- [x] **Ctrl+O** / **Ctrl+Shift+O** — выбрать файлы/папку
- [x] **Ctrl+.** — открыть папку, **Space** — play/pause
- [x] **Esc** — отменить / очистить

### Локализация + темы + About ✅
- [x] **RU/EN** — переключение кнопкой, сохранение в ConfigManager
- [x] **Три темы** — тёмная / светлая / системная
- [x] **About-диалог** — лицензии, компоненты, благодарности
- [x] **Переименование** → MO Kolomyagi Media Converter
- [x] **Иконка** ▶→📄 (генерация через PIL)

### Сборка .exe ✅
- [x] **scripts/build-win.bat** — PyInstaller под Windows
- [x] Включает ffmpeg/ffprobe, PySide6, pillow-heif

### В плане 📋
- [ ] **Автоматическое определение формата** по превью

## Архитектура GUI

Единая реализация Qt6, общее ядро (`core.py`, `cli.py`, `history.py`):

```
src/conv/gui/
├── __init__.py          # run_gui()
├── app.py               # ConvApp (QMainWindow)
├── theme.py             # QPalette + QSS (тёмная/светлая/системная)
├── i18n.py              # RU/EN переводы
├── about.py             # Окно «О программе»
├── resources/
│   ├── icon.ico         # Иконка для .exe
│   └── icon.svg         # Исходник иконки
├── widgets/
│   ├── params.py        # формат, качество, размер, пресет
│   ├── file_table.py    # QTreeView + чекбоксы + DnD
│   ├── preview.py       # PIL-превью + QVideoPlayer + таймлайн
│   └── timeline.py      # IN/OUT маркеры, waveform, range-drag
└── controllers/
    └── conversion.py    # QThread-воркер
```

**Что изменилось:** Tkinter (CustomTkinter) удалён. Единственный GUI — Qt6 (PySide6).
Путь установки: `pip install conv[gui]`, запуск: `conv-gui`.

**Принципы:**
- Каждый виджет — самодостаточный класс с коллбэками наружу
- `ConvApp` только собирает готовые части и связывает сигналами
- Новые фичи ложатся в свои виджеты без правок существующих
- Точка входа `conv.gui:run_gui` не меняется

> *"Хороший план сегодня лучше идеального завтра"*
> — Иохим Кузьмич 🖧
