"""conv GUI — Flet-интерфейс."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import flet as ft
except ImportError:
    print("Flet не установлен. Установи: pip install conv[gui]")
    sys.exit(1)

from conv.core import (
    Converter,
    ConvertRequest,
    ConvertResult,
    OUTPUT_FORMATS,
    detect_mime,
    resolve_format,
)


def main(page: ft.Page):
    # ── Настройки страницы ────────────────────────────────────────────────
    page.title = "🖧 conv — Иохим Кузьмич"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 20
    page.window_width = 800
    page.window_height = 700
    page.window_min_width = 600
    page.window_min_height = 500

    # ── Цвета ─────────────────────────────────────────────────────────────
    BG = "#0a0a2e"
    SURFACE = "#1a1a3e"
    ACCENT = "#00d4ff"
    ACCENT2 = "#7b2ff7"
    SUCCESS = "#00e676"
    ERROR = "#ff1744"

    page.bgcolor = BG

    # ── Состояние ─────────────────────────────────────────────────────────
    converter = Converter()
    files: list[Path] = []
    results: list[ConvertResult] = []
    is_running = False

    # ── Элементы интерфейса ───────────────────────────────────────────────

    # Drag'n'drop область
    drop_area = ft.Container(
        content=ft.Column([
            ft.Icon(ft.icons.CLOUD_UPLOAD_ROUNDED, size=48, color=ACCENT),
            ft.Text("Перетащите файлы сюда", size=16, color=ACCENT),
            ft.Text("или", size=12, color=ACCENT, opacity=0.6),
            ft.ElevatedButton("Выбрать файлы",
                              icon=ft.icons.FOLDER_OPEN,
                              style=ft.ButtonStyle(color=ACCENT)),
        ], alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        height=120,
        border_radius=12,
        border=ft.border.all(1, ACCENT + "40"),
        gradient=ft.LinearGradient(
            begin=ft.alignment.top_left,
            end=ft.alignment.bottom_right,
            colors=[SURFACE, BG],
        ),
        ink=True,
    )

    # Список файлов
    file_list = ft.ListView(spacing=4, height=200, auto_scroll=True)

    # Формат
    format_dropdown = ft.Dropdown(
        label="Выходной формат",
        options=[
            ft.dropdown.Option("auto", "Авто"),
            *[ft.dropdown.Option(k, v['desc']) for k, v in OUTPUT_FORMATS.items()],
        ],
        value="auto",
        width=200,
    )

    # Качество
    quality_slider = ft.Slider(
        min=1, max=100, value=85,
        divisions=99,
        label="{value}%",
        width=200,
    )
    quality_label = ft.Text("85", size=14, color=ACCENT)

    # Размер (макс. px)
    size_field = ft.TextField(
        label="Макс. px (0 = оригинал)",
        value="0",
        width=150,
        keyboard_type=ft.KeyboardType.NUMBER,
    )

    # Прогресс
    progress_bar = ft.ProgressBar(width=0, height=6, color=ACCENT, bgcolor=SURFACE)
    status_text = ft.Text("Ожидание...", size=12, color=ft.colors.GREY_400)
    stats_text = ft.Text("", size=12, color=ft.colors.GREY_500)

    # Кнопки
    convert_btn = ft.ElevatedButton(
        "⚡ Конвертировать",
        icon=ft.icons.PLAY_ARROW_ROUNDED,
        style=ft.ButtonStyle(bgcolor=ACCENT, color=BG),
        disabled=True,
    )
    clear_btn = ft.FilledTonalButton(
        "Очистить",
        icon=ft.icons.DELETE_OUTLINE,
        style=ft.ButtonStyle(color=ft.colors.GREY_400),
    )

    # ── Обработчики ───────────────────────────────────────────────────────

    def update_ui():
        convert_btn.disabled = len(files) == 0 or is_running
        clear_btn.disabled = len(files) == 0 or is_running
        progress_bar.width = 400 if is_running else 0
        page.update()

    def on_drop(e: ft.DragTargetEvent):
        nonlocal files
        if is_running:
            return
        for path_str in (e.data or "").split("\n"):
            path_str = path_str.strip().strip('"').strip("'")
            if path_str:
                p = Path(path_str)
                if p.exists() and p.suffix.lower() in __import__('conv.core').ALL_INPUT:
                    if p not in files:
                        files.append(p)
        _refresh_file_list()
        update_ui()

    def pick_files(e):
        nonlocal files
        if is_running:
            return

        def on_pick(e: ft.FilePickerResultEvent):
            nonlocal files
            if e.files:
                for f in e.files:
                    p = Path(f.path)
                    if p.exists() and p.suffix.lower() in __import__('conv.core').ALL_INPUT:
                        if p not in files:
                            files.append(p)
                _refresh_file_list()
                update_ui()

        page.dialog = ft.FilePicker(on_result=on_pick)
        page.dialog.pick_files(allow_multiple=True,
                                file_type=ft.FilePickerFileType.CUSTOM,
                                allowed_extensions=list(__import__('conv.core').ALL_INPUT))

    def remove_file(file_path: Path):
        if file_path in files and not is_running:
            files.remove(file_path)
            _refresh_file_list()
            update_ui()

    def _refresh_file_list():
        file_list.controls.clear()
        for f in files:
            ext = f.suffix.lower()
            sym = "🖼" if ext not in (__import__('conv.core').VIDEO_INPUT | __import__('conv.core').AUDIO_INPUT) else \
                  "🎬" if ext in __import__('conv.core').VIDEO_INPUT else "🎵"
            file_list.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Text(f"{sym} {f.name}", size=13, expand=True),
                        ft.Text(f"{(f.stat().st_size / 1024):.0f} KB",
                                size=11, color=ft.colors.GREY_500),
                        ft.IconButton(
                            ft.icons.CLOSE,
                            icon_size=16,
                            icon_color=ft.colors.GREY_500,
                            on_click=lambda _, p=f: remove_file(p),
                        ),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    padding=5,
                    border_radius=6,
                    bgcolor=SURFACE,
                    margin=ft.margin.symmetric(vertical=2),
                )
            )
        page.update()

    def on_quality_change(e):
        quality_label.value = f"{int(e.control.value)}"
        page.update()

    def convert_start(e):
        nonlocal is_running, results
        if is_running or not files:
            return

        is_running = True
        results = []
        convert_btn.text = "⏳ Конвертируется..."
        status_text.value = f"0/{len(files)}"
        status_text.color = ACCENT
        update_ui()

        # Параметры
        fmt = format_dropdown.value if format_dropdown.value != "auto" else ''
        quality = int(quality_slider.value)
        max_size = int(size_field.value or '0')

        out_dir = Path.cwd() / "CONVERTED"
        out_dir.mkdir(exist_ok=True, parents=True)

        # Создаём запросы
        requests = [
            ConvertRequest(f, out_dir, output_format=fmt,
                           quality=quality, max_size=max_size)
            for f in files
        ]

        total = len(requests)

        def on_progress(current, total, result):
            status_text.value = f"{current}/{total}"
            progress_bar.value = current / total
            results.append(result)
            page.update()

        # Запуск в отдельном потоке
        import threading

        def run():
            nonlocal is_running
            try:
                results.clear()
                converter.convert_many(requests, on_progress=on_progress)

                # Итог
                ok = sum(1 for r in results if r.ok)
                fail = total - ok
                status_text.value = f"✅ {ok}/{total}" if fail == 0 else f"✅ {ok}/{total} ❌ {fail}"
                status_text.color = SUCCESS if fail == 0 else ft.colors.ORANGE_400

                # Статистика
                total_src = sum(r.src_size for r in results)
                total_dst = sum(r.dst_size for r in results if r.ok)
                stats_text.value = (f"📦 {_fmt_size(total_src)} → {_fmt_size(total_dst)}"
                                    f"  ({total_dst/total_src*100:.0f}%)"
                                    if total_src > 0 else "")
            except Exception as ex:
                status_text.value = f"❌ Ошибка: {ex}"
                status_text.color = ERROR
            finally:
                is_running = False
                convert_btn.text = "⚡ Конвертировать"
                progress_bar.value = 1.0
                page.update()

        threading.Thread(target=run, daemon=True).start()

    # ── Сборка layout ─────────────────────────────────────────────────────

    # Header
    header = ft.Container(
        content=ft.Row([
            ft.Text("🖧  conv", size=28, weight=ft.FontWeight.BOLD,
                    color=ACCENT),
            ft.Text("Иохим Кузьмич Media Converter", size=13,
                    color=ft.colors.GREY_500),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        margin=ft.margin.only(bottom=20),
    )

    # Параметры
    params = ft.Container(
        content=ft.Row([
            format_dropdown,
            ft.Column([
                ft.Row([
                    ft.Text("Качество:", size=12, color=ft.colors.GREY_400),
                    quality_label,
                ]),
                quality_slider,
            ], tight=True, spacing=0),
            size_field,
        ], spacing=20, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=10,
        border_radius=8,
        bgcolor=SURFACE,
        margin=ft.margin.only(top=10, bottom=10),
    )

    # Кнопки
    buttons = ft.Row([
        convert_btn,
        clear_btn,
        status_text,
    ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    # Статус
    status_bar = ft.Row([
        progress_bar,
        stats_text,
    ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    # Привязка событий
    drop_area.on_click = pick_files
    quality_slider.on_change = on_quality_change
    convert_btn.on_click = convert_start

    def clear_all(e):
        nonlocal files, results
        if is_running:
            return
        files.clear()
        results.clear()
        file_list.controls.clear()
        status_text.value = "Ожидание..."
        status_text.color = ft.colors.GREY_400
        stats_text.value = ""
        progress_bar.value = 0
        page.update()

    clear_btn.on_click = clear_all

    # Финальный layout
    page.add(
        header,
        drop_area,
        params,
        file_list,
        buttons,
        status_bar,
    )

    page.update()


def _fmt_size(b: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.2f} TB"


if __name__ == '__main__':
    ft.app(target=main)
