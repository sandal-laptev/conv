"""conv GUI — Flet-интерфейс (Flet 0.85+)."""

from __future__ import annotations

import asyncio
import os
import threading
import time
from pathlib import Path

import flet as ft

from conv.core import (
    Converter,
    ConvertRequest,
    ConvertResult,
    OUTPUT_FORMATS,
    VIDEO_INPUT,
    AUDIO_INPUT,
    ALL_INPUT,
)


# ──────────────────────────────────────────────────────────────────────────────
# Константы
# ──────────────────────────────────────────────────────────────────────────────

COLORS = {
    "bg": "#0a0a2e",
    "surface": "#1a1a3e",
    "surface2": "#252550",
    "accent": "#00d4ff",
    "accent2": "#7b2ff7",
    "success": "#00e676",
    "error": "#ff1744",
    "warning": "#ffab00",
    "text": "#e0e0e0",
    "text2": "#9e9e9e",
    "text3": "#616161",
}

FORMAT_OPTIONS = [("auto", "Авто")] + [
    (k, v["desc"]) for k, v in OUTPUT_FORMATS.items()
]


# ──────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции
# ──────────────────────────────────────────────────────────────────────────────

def fmt_size(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.2f} TB"


def fmt_time(s: float) -> str:
    if s < 60:
        return f"{s:.1f}с"
    m, r = divmod(s, 60)
    if m < 60:
        return f"{int(m)}м {r:.0f}с"
    h, m = divmod(m, 60)
    return f"{int(h)}ч {int(m)}м"


def file_icon(ext: str) -> str:
    if ext in VIDEO_INPUT:
        return ft.Icons.VIDEO_LIBRARY
    elif ext in AUDIO_INPUT:
        return ft.Icons.AUDIOTRACK
    return ft.Icons.IMAGE


def sym_for(ext: str) -> str:
    if ext in VIDEO_INPUT:
        return "🎬"
    elif ext in AUDIO_INPUT:
        return "🎵"
    return "🖼"


def border_all(width: float, color: str) -> ft.Border:
    """Создаёт Border со всех сторон (замена ft.border.all)."""
    s = ft.BorderSide(width, color)
    return ft.Border(left=s, top=s, right=s, bottom=s)


# ──────────────────────────────────────────────────────────────────────────────
# Главное приложение
# ──────────────────────────────────────────────────────────────────────────────

async def main(page: ft.Page):
    page.title = "🖧 conv — Иохим Кузьмич Media Converter"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 20
    page.spacing = 12
    page.window_width = 880
    page.window_height = 780
    page.window_min_width = 700
    page.window_min_height = 600
    page.bgcolor = COLORS["bg"]

    page.theme = ft.Theme(
        color_scheme_seed=COLORS["accent"],
        use_material3=True,
    )

    # ── FilePicker (создаём один раз, добавляем на страницу) ──────────────
    file_picker = ft.FilePicker()
    page.add(file_picker)

    # ── Состояние ─────────────────────────────────────────────────────────
    converter = Converter()
    file_paths: list[Path] = []
    file_results: dict[Path, ConvertResult] = {}
    is_running = False
    cancel_flag = False

    # ── DragTarget зона ───────────────────────────────────────────────────

    drag_text = ft.Text(
        "Перетащите файлы сюда или нажмите для выбора",
        size=15, color=COLORS["text2"],
    )
    drag_subtext = ft.Text(
        "Поддерживаются изображения, SVG, видео, аудио",
        size=11, color=COLORS["text3"],
    )
    drag_icon = ft.Icon(ft.Icons.CLOUD_UPLOAD, size=44, color=COLORS["accent"])
    drag_col = ft.Column(
        [drag_icon, drag_text, drag_subtext],
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=6,
    )

    drag_container = ft.Container(
        content=drag_col,
        height=130,
        border_radius=14,
        bgcolor=COLORS["surface"],
        border=border_all(1.5, COLORS["accent"] + "40"),
        ink=True,
    )

    def drag_highlight(on: bool):
        if on:
            drag_container.border = border_all(2, COLORS["accent"])
            drag_container.bgcolor = COLORS["surface2"]
            drag_icon.color = COLORS["accent2"]
            drag_text.value = "📥 Отпустите файлы для добавления"
            drag_text.color = COLORS["accent"]
        else:
            drag_container.border = border_all(1.5, COLORS["accent"] + "40")
            drag_container.bgcolor = COLORS["surface"]
            drag_icon.color = COLORS["accent"]
            drag_text.value = "Перетащите файлы сюда или нажмите для выбора"
            drag_text.color = COLORS["text2"]
        page.update()

    drag_target = ft.DragTarget(
        content=drag_container,
        on_accept=lambda e: _on_drop(e),
        on_leave=lambda _: drag_highlight(False),
    )

    def _on_drop(e):
        drag_highlight(False)
        if e.data:
            raw = e.data.strip().split("\n")
            paths = []
            for rp in raw:
                rp = rp.strip().strip('"').strip("'")
                if rp:
                    p = Path(rp)
                    if p.exists() and p.suffix.lower() in ALL_INPUT:
                        paths.append(p)
            add_files(paths)

    async def pick_files(_e):
        if is_running:
            return

        files = await file_picker.pick_files(
            allow_multiple=True,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=list(ALL_INPUT),
        )

        if files:
            paths = [Path(f.path) for f in files]
            add_files(paths)

    drag_container.on_click = pick_files

    # ── Список файлов ─────────────────────────────────────────────────────

    file_list_view = ft.ListView(spacing=4, auto_scroll=True, height=240)

    def refresh_file_list():
        file_list_view.controls.clear()
        for p in file_paths:
            ext = p.suffix.lower()
            res = file_results.get(p)

            if res and res.ok:
                status_icon = ft.Icon(ft.Icons.CHECK_CIRCLE, size=18,
                                      color=COLORS["success"])
                info = (f"{fmt_size(res.dst_size)} "
                        f"({res.dst_size / res.src_size * 100:.0f}%) "
                        f"— {res.fmt_took()}")
                info_color = COLORS["text2"]
            elif res and not res.ok:
                status_icon = ft.Icon(ft.Icons.ERROR, size=18, color=COLORS["error"])
                info = res.error[:50]
                info_color = COLORS["error"]
            else:
                status_icon = ft.Icon(ft.Icons.HOURGLASS_EMPTY, size=18,
                                      color=COLORS["text3"])
                info = ""
                info_color = COLORS["text3"]

            row = ft.Row([
                ft.Icon(file_icon(ext), size=20, color=COLORS["accent"]),
                ft.Text(p.name, size=13, color=COLORS["text"], expand=True),
                ft.Text(fmt_size(_size_or_zero(p)), size=11, color=COLORS["text3"]),
                status_icon,
                ft.Text(info, size=11, color=info_color),
                ft.IconButton(
                    ft.Icons.CLOSE, icon_size=16,
                    icon_color=COLORS["text3"],
                    on_click=lambda _, pp=p: remove_file(pp),
                    disabled=is_running,
                ),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)

            idx = file_paths.index(p)
            bg = COLORS["surface"] if idx % 2 == 0 else COLORS["surface2"]
            file_list_view.controls.append(
                ft.Container(content=row,
                             padding=ft.Padding(left=10, top=6, right=10, bottom=6),
                             border_radius=8, bgcolor=bg)
            )
        page.update()

    def _size_or_zero(p: Path) -> int:
        try:
            return p.stat().st_size
        except OSError:
            return 0

    def add_files(paths: list[Path]):
        if is_running:
            return
        existing = set(file_paths)
        for p in paths:
            if p not in existing:
                file_paths.append(p)
        refresh_file_list()
        update_buttons()

    def remove_file(p: Path):
        if is_running:
            return
        if p in file_paths:
            file_paths.remove(p)
            file_results.pop(p, None)
        refresh_file_list()
        update_buttons()

    def clear_all(_e=None):
        if is_running:
            return
        file_paths.clear()
        file_results.clear()
        refresh_file_list()
        update_buttons()
        status_main.value = "Ожидание файлов..."
        status_sub.value = ""
        progress_bar.value = 0
        page.update()

    # ── Параметры ─────────────────────────────────────────────────────────

    format_dropdown = ft.Dropdown(
        label="Формат", hint_text="Авто",
        options=[ft.dropdown.Option(k, v) for k, v in FORMAT_OPTIONS],
        value="auto", width=160, dense=True,
    )

    quality_slider = ft.Slider(
        min=1, max=100, value=85, divisions=99,
        label="{value}%", width=180,
    )
    quality_label = ft.Text("85%", size=13, color=COLORS["accent"])

    def on_quality_change(e):
        quality_label.value = f"{int(e.control.value)}%"
        page.update()

    quality_slider.on_change = on_quality_change

    size_field = ft.TextField(
        label="Макс. px", hint_text="0 = ориг.",
        value="0", width=110, dense=True,
        keyboard_type=ft.KeyboardType.NUMBER,
    )

    # ── Конвертация ───────────────────────────────────────────────────────

    progress_bar = ft.ProgressBar(
        width=0, height=6, color=COLORS["accent"], bgcolor=COLORS["surface"],
    )
    status_main = ft.Text("Ожидание файлов...", size=14, color=COLORS["text2"])
    status_sub = ft.Text("", size=12, color=COLORS["text3"])

    convert_btn = ft.ElevatedButton(
        "⚡ Конвертировать",
        icon=ft.Icons.PLAY_ARROW,
        style=ft.ButtonStyle(
            bgcolor=COLORS["accent"], color=COLORS["bg"],
            shape=ft.RoundedRectangleBorder(radius=10),
        ),
        disabled=True,
    )
    clear_btn = ft.OutlinedButton(
        "Очистить", icon=ft.Icons.DELETE,
        style=ft.ButtonStyle(color=COLORS["text3"]),
        disabled=True,
    )
    open_btn = ft.OutlinedButton(
        "Открыть папку", icon=ft.Icons.FOLDER,
        style=ft.ButtonStyle(color=COLORS["text3"]),
        visible=False,
    )

    def update_buttons():
        has = len(file_paths) > 0
        convert_btn.disabled = not has or is_running
        clear_btn.disabled = not has or is_running
        page.update()

    def open_output(_e):
        out_dir = Path.cwd() / "CONVERTED"
        if out_dir.exists():
            if os.name == "posix":
                os.system(f'xdg-open "{out_dir}"')
            else:
                os.system(f'start "" "{out_dir}"')

    open_btn.on_click = open_output

    # ── Процесс конвертации ───────────────────────────────────────────────

    def do_convert(_e):
        nonlocal is_running, cancel_flag
        if is_running or not file_paths:
            return

        is_running = True
        cancel_flag = False
        file_results.clear()

        fmt = format_dropdown.value if format_dropdown.value != "auto" else ""
        quality = int(quality_slider.value)
        max_size = int(size_field.value or "0")

        out_dir = Path.cwd() / "CONVERTED"
        out_dir.mkdir(exist_ok=True, parents=True)

        requests = [
            ConvertRequest(p, out_dir, output_format=fmt,
                           quality=quality, max_size=max_size)
            for p in file_paths
        ]

        total = len(requests)
        done = 0
        start_time = time.time()

        status_main.value = "⏳ Конвертация..."
        status_main.color = COLORS["accent"]
        progress_bar.width = 600
        progress_bar.value = 0.0
        convert_btn.text = "⏹ Отмена"
        convert_btn.style = ft.ButtonStyle(
            bgcolor=COLORS["error"], color="#fff",
            shape=ft.RoundedRectangleBorder(radius=10),
        )
        open_btn.visible = False
        update_buttons()
        refresh_file_list()

        def cancel_click(_e2):
            nonlocal cancel_flag
            cancel_flag = True

        convert_btn.on_click = cancel_click

        def run():
            nonlocal is_running, done
            try:
                for req in requests:
                    if cancel_flag:
                        break
                    res = converter.convert_one(req)
                    file_results[req.input_path] = res
                    done += 1

                    # UI update
                    elapsed = time.time() - start_time
                    eta = (elapsed / done * (total - done)) if done > 0 else 0
                    status_main.value = (
                        f"⏳ {done}/{total}  ({fmt_time(elapsed)} / ~{fmt_time(eta)})"
                    )
                    progress_bar.value = done / total
                    refresh_file_list()
            finally:
                is_running = False

            # Итог
            ok = sum(1 for p in file_paths
                     if file_results.get(p) and file_results[p].ok)
            fail = total - done if cancel_flag else total - ok

            if cancel_flag and done == 0:
                status_main.value = "⏹ Отменено"
                status_main.color = COLORS["warning"]
            elif fail == 0:
                status_main.value = f"✅ Готово: {ok}/{total}"
                status_main.color = COLORS["success"]
                open_btn.visible = True
            else:
                status_main.value = f"✅ {ok}/{total}  ❌ {fail}/{total}"
                status_main.color = COLORS["warning"]
                open_btn.visible = ok > 0

            total_src = sum(
                file_results[p].src_size for p in file_paths if file_results.get(p)
            )
            total_dst = sum(
                file_results[p].dst_size for p in file_paths
                if file_results.get(p) and file_results[p].ok
            )
            total_time = sum(
                file_results[p].took for p in file_paths if file_results.get(p)
            )
            if total_src > 0:
                pct = total_dst / total_src * 100 if total_dst > 0 else 0
                status_sub.value = (
                    f"📦 {fmt_size(total_src)} → {fmt_size(total_dst)} "
                    f"({pct:.0f}%)  ⏱ {fmt_time(total_time)}"
                )
            else:
                status_sub.value = ""

            progress_bar.value = 1.0
            convert_btn.text = "⚡ Конвертировать"
            convert_btn.style = ft.ButtonStyle(
                bgcolor=COLORS["accent"], color=COLORS["bg"],
                shape=ft.RoundedRectangleBorder(radius=10),
            )
            convert_btn.on_click = do_convert
            update_buttons()
            refresh_file_list()
            page.update()

        threading.Thread(target=run, daemon=True).start()

    convert_btn.on_click = do_convert
    clear_btn.on_click = clear_all

    # ── Layout ─────────────────────────────────────────────────────────────

    header = ft.Container(
        content=ft.Row([
            ft.Row([
                ft.Text("🖧", size=30),
                ft.Text("conv", size=28, weight=ft.FontWeight.BOLD,
                        color=COLORS["accent"]),
            ], spacing=6),
            ft.Text("Иохим Кузьмич Media Converter", size=13,
                    color=COLORS["text3"]),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        margin=ft.Margin(left=0, top=0, right=0, bottom=8),
    )

    params_panel = ft.Container(
        content=ft.Row([
            format_dropdown,
            ft.Column([
                ft.Row([
                    ft.Text("Качество:", size=12, color=COLORS["text3"]),
                    quality_label,
                ], spacing=4),
                quality_slider,
            ], tight=True, spacing=0),
            size_field,
        ], spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding(left=14, top=8, right=14, bottom=8),
        border_radius=10, bgcolor=COLORS["surface"],
        margin=ft.Margin(left=0, top=6, right=0, bottom=6),
    )

    status_bar = ft.Column([
        ft.Row([progress_bar]),
        ft.Row([
            status_main, status_sub, open_btn,
        ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
    ], spacing=4)

    btn_row = ft.Row([convert_btn, clear_btn], spacing=10)

    page.add(header, drag_target, params_panel, file_list_view, btn_row, status_bar)
    page.update()


def main_flet():
    """Точка входа для console_scripts."""
    ft.run(main=main)


if __name__ == "__main__":
    main_flet()
