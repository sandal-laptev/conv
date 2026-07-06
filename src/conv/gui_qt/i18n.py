"""i18n — переводы RU/EN для GUI."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LangStrings:
    """Все строки интерфейса для одного языка."""

    # Окно
    window_title: str = ""
    header: str = ""

    # Кнопки тулбара
    btn_select_files: str = ""
    btn_select_folder: str = ""
    btn_clear: str = ""
    btn_select_all: str = ""
    btn_deselect_all: str = ""
    btn_invert: str = ""
    btn_check_tools: str = ""
    btn_logs: str = ""
    btn_about: str = ""

    # Параметры
    label_preset: str = ""
    label_format: str = ""
    label_quality: str = ""
    label_max_px: str = ""
    checkbox_sort: str = ""
    checkbox_rename: str = ""
    preset_custom: str = ""
    format_auto: str = ""

    # Выход
    output_label: str = ""

    # Конвертация
    btn_convert: str = ""
    btn_cancel: str = ""
    btn_open_folder: str = ""
    status_waiting: str = ""
    status_no_files: str = ""
    status_select_format: str = ""
    status_renaming: str = ""
    status_renamed: str = ""
    status_converting: str = ""
    status_cancelling: str = ""
    status_cancelled: str = ""
    status_ready: str = ""
    status_no_selection: str = ""

    # Таблица
    col_file: str = ""
    col_size: str = ""
    col_format: str = ""
    col_status: str = ""
    col_result: str = ""
    drop_hint: str = ""
    drop_hint_sub: str = ""
    drag_overlay: str = ""
    no_preview: str = ""
    no_duration: str = ""

    # Контекстное меню
    menu_check: str = ""
    menu_uncheck: str = ""
    menu_check_all: str = ""
    menu_uncheck_all: str = ""
    menu_invert: str = ""
    menu_remove_file: str = ""
    menu_remove_checked: str = ""
    menu_set_format: str = ""
    menu_set_format_auto: str = ""

    # Таймлайн
    timeline_title: str = ""
    timeline_in: str = ""
    timeline_out: str = ""
    timeline_reset: str = ""

    # Превью / видео
    duration: str = ""
    bitrate: str = ""
    video: str = ""
    audio: str = ""
    audio_placeholder: str = ""
    video_placeholder: str = ""
    no_preview_text: str = ""

    # About
    about_title: str = ""
    about_version: str = ""
    about_license: str = ""
    about_credits: str = ""
    about_tech: str = ""
    about_thanks: str = ""

    # Язык / тема
    lang_ru: str = ""
    lang_en: str = ""
    theme_dark: str = ""
    theme_light: str = ""
    theme_system: str = ""

    # Инструменты
    tools_title: str = ""
    tools_missing: str = ""
    tools_tips: str = ""


RU: LangStrings = LangStrings(
    window_title="🖧  MO Kolomyagi Media Converter",
    header="🖧  MO Kolomyagi — Media Converter",
    btn_select_files="📂 Выбрать файлы",
    btn_select_folder="📁 Выбрать папку (рекурсивно)",
    btn_clear="🗑 Очистить",
    btn_select_all="✅ Всё",
    btn_deselect_all="❌ Снять",
    btn_invert="🔀 Инверт.",
    btn_check_tools="🔧 Проверить",
    btn_logs="📋 Логи",
    btn_about="ℹ О программе",
    label_preset="Пресет:",
    label_format="Формат:",
    label_quality="Качество:",
    label_max_px="Макс. px (0 = ориг):",
    checkbox_sort="📁 Сортировать по типу (image/video/audio)",
    checkbox_rename="🔄 Только переименовать (без конвертации)",
    preset_custom="— Кастом",
    format_auto="Авто",
    output_label="📁 Выход:",
    btn_convert="⚡ Конвертировать",
    btn_cancel="⏹ Отмена",
    btn_open_folder="📂 Открыть папку",
    status_waiting="Ожидание файлов...",
    status_no_files="(нет файлов)",
    status_select_format="⚠ Выберите формат для переименования",
    status_renaming="⏳ Переименование...",
    status_renamed="✅ Переименовано:",
    status_converting="⏳ Конвертация...",
    status_cancelling="⏹ Отмена...",
    status_cancelled="⏹ Отменено",
    status_ready="✅ Готово:",
    status_no_selection="⚠ Нет выделенных файлов для конвертации",
    col_file="Файл",
    col_size="Размер",
    col_format="→ формат",
    col_status="Статус",
    col_result="Результат",
    drop_hint="📂  Перетащите файлы сюда",
    drop_hint_sub="или нажмите «Выбрать файлы» сверху",
    drag_overlay="📂 Отпустите файлы для добавления",
    no_preview="(нет превью)",
    no_duration="Нет данных о длительности",
    menu_check="✅ Выделить",
    menu_uncheck="✅ Снять",
    menu_check_all="✅ Выделить все",
    menu_uncheck_all="❌ Снять всё",
    menu_invert="🔀 Инвертировать",
    menu_remove_file="🗑 Удалить файл",
    menu_remove_checked="🗑 Удалить выделенные чекбоксом",
    menu_set_format="🎞 Задать формат выделенным",
    menu_set_format_auto="Авто",
    timeline_title="✂ Обрезка (IN / OUT)",
    timeline_in="IN:",
    timeline_out="OUT:",
    timeline_reset="↺ Сброс",
    duration="⏱ Длительность:",
    bitrate="📊 Битрейт:",
    video="🎞 Видео:",
    audio="🎵 Аудио:",
    audio_placeholder="🎵 (аудио — waveform на таймлайне)",
    video_placeholder="🎬 (предпросмотр видео)",
    no_preview_text="🖼 (нет превью)",
    about_title="О программе",
    about_version="Версия",
    about_license="Лицензия: GNU GPLv3+",
    about_credits="",
    about_tech="",
    about_thanks="",
    lang_ru="🇷🇺 RU",
    lang_en="🇬🇧 EN",
    theme_dark="🌙 Тёмная",
    theme_light="☀️ Светлая",
    theme_system="💻 Системная",
    tools_title="🔧 Проверка инструментов",
    tools_missing="\n⚠ Отсутствуют:",
    tools_tips="",
)

EN: LangStrings = LangStrings(
    window_title="🖧  MO Kolomyagi Media Converter",
    header="🖧  MO Kolomyagi — Media Converter",
    btn_select_files="📂 Select Files",
    btn_select_folder="📁 Select Folder (recursive)",
    btn_clear="🗑 Clear",
    btn_select_all="✅ All",
    btn_deselect_all="❌ None",
    btn_invert="🔀 Invert",
    btn_check_tools="🔧 Check Tools",
    btn_logs="📋 Logs",
    btn_about="ℹ About",
    label_preset="Preset:",
    label_format="Format:",
    label_quality="Quality:",
    label_max_px="Max px (0 = original):",
    checkbox_sort="📁 Sort by type (image/video/audio)",
    checkbox_rename="🔄 Rename only (no conversion)",
    preset_custom="— Custom",
    format_auto="Auto",
    output_label="📁 Output:",
    btn_convert="⚡ Convert",
    btn_cancel="⏹ Cancel",
    btn_open_folder="📂 Open Folder",
    status_waiting="Waiting for files...",
    status_no_files="(no files)",
    status_select_format="⚠ Select a format for renaming",
    status_renaming="⏳ Renaming...",
    status_renamed="✅ Renamed:",
    status_converting="⏳ Converting...",
    status_cancelling="⏹ Cancelling...",
    status_cancelled="⏹ Cancelled",
    status_ready="✅ Done:",
    status_no_selection="⚠ No files selected for conversion",
    col_file="File",
    col_size="Size",
    col_format="→ format",
    col_status="Status",
    col_result="Result",
    drop_hint="📂  Drop files here",
    drop_hint_sub="or click «Select Files» above",
    drag_overlay="📂 Release to add files",
    no_preview="(no preview)",
    no_duration="No duration data",
    menu_check="✅ Check",
    menu_uncheck="✅ Uncheck",
    menu_check_all="✅ Check All",
    menu_uncheck_all="❌ Uncheck All",
    menu_invert="🔀 Invert",
    menu_remove_file="🗑 Remove File",
    menu_remove_checked="🗑 Remove Checked",
    menu_set_format="🎞 Set Format for Checked",
    menu_set_format_auto="Auto",
    timeline_title="✂ Trim (IN / OUT)",
    timeline_in="IN:",
    timeline_out="OUT:",
    timeline_reset="↺ Reset",
    duration="⏱ Duration:",
    bitrate="📊 Bitrate:",
    video="🎞 Video:",
    audio="🎵 Audio:",
    audio_placeholder="🎵 (audio — waveform in timeline below)",
    video_placeholder="🎬 (video preview)",
    no_preview_text="🖼 (no preview)",
    about_title="About",
    about_version="Version",
    about_license="License: GNU GPLv3+",
    about_credits="",
    about_tech="",
    about_thanks="",
    lang_ru="🇷🇺 RU",
    lang_en="🇬🇧 EN",
    theme_dark="🌙 Dark",
    theme_light="☀️ Light",
    theme_system="💻 System",
    tools_title="🔧 Tool Check",
    tools_missing="\n⚠ Missing:",
    tools_tips="",
)


# Текущий язык (глобально)
_current: LangStrings = RU


def set_lang(lang: str) -> None:
    global _current
    _current = RU if lang == "ru" else EN


def _(key: str) -> str:
    """Получить перевод по ключу."""
    return getattr(_current, key, f"!{key}!")
