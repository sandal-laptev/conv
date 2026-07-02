"""conv GUI — Flet-интерфейс."""

from __future__ import annotations

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
    detect_mime,
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
        return ft.icons.VIDEO_FILE_ROUNDED
    elif ext in AUDIO_INPUT:
        return ft.icons.AUDIO_FILE_ROUNDED
    else:
        return ft.icons.IMAGE_ROUNDED


def sym_for(ext: str) -> str:
    if ext in VIDEO_INPUT:
        return "🎬"
    elif ext in AUDIO_INPUT:
        return "🎵"
    return "🖼"


# ──────────────────────────────────────────────────────────────────────────────
# Главное приложение
# ──────────────────────────────────────────────────────────────────────────────

def main(page: ft.Page):
    # Проверка версии Flet
    try:
        from flet.version import version as fv
        flet_ver = tuple(int(x) for x in fv.split("."))
        if flet_ver < (0, 21, 0):
            page.add(ft.Text(
                f"❌ Flet {fv} устарел. Обнови: pip install -U flet",
                color=COLORS["error"], size=14,
            ))
            page.update()
            return
    except (ImportError, ValueError, AttributeError):
        pass  # не можем проверить — пробуем запустить

    page.title = "🖧 conv — Иохим Кузьмич Media Converter"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 20
    page.spacing = 12
    page.window_width = 880
    page.window_height = 780
    page.window_min_width = 700
    page.window_min_height = 600
    page.bgcolor = COLORS["bg"]

    # ── Состояние ─────────────────────────────────────────────────────────
    converter = Converter()
    file_entries: list[dict] = []  # {path: Path, result: ConvertResult | None}
    is_running = False
    cancel_flag = False

    # ── Тема ───────────────────────────────────────────────────────────────
    page.theme = ft.Theme(
        color_scheme_seed=COLORS["accent"],
        use_material3=True,
    )

    # ── DragTarget область ─────────────────────────────────────────────────
    drag_text = ft.Text(
        "Перетащите файлы сюда или нажмите для выбора",
        size=15, color=COLORS["text2"],
    )
    drag_subtext = ft.Text(
        "Поддерживаются изображения, SVG, видео, аудио",
        size=11, color=COLORS["text3"],
    )
    drag_icon = ft.Icon(ft.icons.CLOUD_UPLOAD_ROUNDED, size=44, color=COLORS["accent"])

    drag_container = ft.Container(
        content=ft.Column(
            [drag_icon, drag_text, drag_subtext],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=6,
        ),
        height=130,
        border_radius=14,
        bgcolor=COLORS["surface"],
        border=ft.border.all(1.5, COLORS["accent"] + "40"),
        ink=True,
        animate=ft.animation.Animation(200, "easeInOut"),
    )

    # ── Список файлов ─────────────────────────────────────────────────────
    file_list_view = ft.ListView(spacing=4, auto_scroll=True, height=240)

    def refresh_file_list():
        file_list_view.controls.clear()
        for entry in file_entries:
            p: Path = entry["path"]
            ext = p.suffix.lower()
            res: ConvertResult | None = entry.get("result")

            status_icon = ft.Icon(
                ft.icons.CHECK_CIRCLE_OUTLINE if res and res.ok else
                ft.icons.ERROR_OUTLINE if res and not res.ok else
                ft.icons.HOURGLASS_TOP,
                size=18,
                color=COLORS["success"] if res and res.ok else
                      COLORS["error"] if res and not res.ok else
                      COLORS["text3"],
            )
            size_text = ft.Text(fmt_size(p.stat().st_size), size=11,
                                color=COLORS["text3"])
            result_text = ft.Text("", size=11, color=COLORS["text2"])

            if res:
                if res.ok and res.output_path:
                    result_text.value = (
                        f"{fmt_size(res.dst_size)} ({res.dst_size / res.src_size * 100:.0f}%) "
                        f"— {res.fmt_took()}"
                    )
                    result_text.color = COLORS["text2"]
                elif not res.ok:
                    result_text.value = res.error[:50]
                    result_text.color = COLORS["error"]

            row_parts = [
                ft.Icon(file_icon(ext), size=20, color=COLORS["accent"]),
                ft.Text(p.name, size=13, color=COLORS["text"], expand=True),
                size_text,
                status_icon,
                result_text,
                ft.IconButton(
                    ft.icons.CLOSE,
                    icon_size=16,
                    icon_color=COLORS["text3"],
                    on_click=lambda _, pp=p: remove_file(pp),
                    disabled=is_running,
                ),
            ]

            file_list_view.controls.append(
                ft.Container(
                    content=ft.Row(row_parts, spacing=8,
                                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.padding.symmetric(horizontal=10, vertical=6),
                    border_radius=8,
                    bgcolor=COLORS["surface"] if (file_entries.index(entry) %
                                                  2 == 0) else COLORS["surface2"],
                    animate=ft.animation.Animation(150, "easeOut"),
                )
            )
        page.update()

    # ── Добавление/удаление файлов ────────────────────────────────────────

    def add_files(paths: list[Path]):
        if is_running:
            return
        existing = {e["path"] for e in file_entries}
        for p in paths:
            if p not in existing and p.suffix.lower() in __import__(
                    "conv.core").ALL_INPUT:
                file_entries.append({"path": p, "result": None})
        refresh_file_list()
        update_buttons()

    def remove_file(p: Path):
        if is_running:
            return
        file_entries[:] = [e for e in file_entries if e["path"] != p]
        refresh_file_list()
        update_buttons()

    def clear_all():
        if is_running:
            return
        file_entries.clear()
        refresh_file_list()
        update_buttons()
        status_main.value = "Ожидание файлов..."
        status_sub.value = ""
        progress_bar.value = 0
        page.update()

    # ── Выбор файлов через диалог ─────────────────────────────────────────

    def pick_files_dialog(e):
        if is_running:
            return

        def on_pick(e: ft.FilePickerResultEvent):
            if e.files:
                paths = [Path(f.path) for f in e.files]
                add_files(paths)

        file_picker = ft.FilePicker(on_result=on_pick)
        page.overlay.append(file_picker)
        page.update()
        file_picker.pick_files(allow_multiple=True)

    drag_container.on_click = pick_files_dialog

    # ── Drag'n'drop через JavaScript ─────────────────────────────────────
    # Для полноценного DnD используем DragTarget
    drag_target = ft.DragTarget(
        content=drag_container,
        on_accept=lambda e: on_drag_accept(e),
        on_enter=lambda e: set_drag_highlight(True),
        on_leave=lambda e: set_drag_highlight(False),
    )

    def set_drag_highlight(active: bool):
        if active:
            drag_container.border = ft.border.all(2, COLORS["accent"])
            drag_container.bgcolor = COLORS["surface2"]
            drag_icon.color = COLORS["accent2"]
            drag_text.value = "📥 Отпустите файлы для добавления"
            drag_text.color = COLORS["accent"]
        else:
            drag_container.border = ft.border.all(1.5, COLORS["accent"] + "40")
            drag_container.bgcolor = COLORS["surface"]
            drag_icon.color = COLORS["accent"]
            drag_text.value = "Перетащите файлы сюда или нажмите для выбора"
            drag_text.color = COLORS["text2"]
        page.update()

    def on_drag_accept(e: ft.DragTargetAcceptEvent):
        set_drag_highlight(False)
        # Flet передаёт данные DragTargetAcceptEvent.data — строка с путями
        if e.data:
            raw_paths = e.data.strip().split("\n")
            paths = []
            for rp in raw_paths:
                rp = rp.strip().strip('"').strip("'")
                if rp:
                    p = Path(rp)
                    if p.exists():
                        paths.append(p)
            add_files(paths)

    # ── Параметры конвертации ─────────────────────────────────────────────

    format_dropdown = ft.Dropdown(
        label="Формат",
        hint_text="Авто",
        options=[ft.dropdown.Option(k, v) for k, v in FORMAT_OPTIONS],
        value="auto",
        width=160,
        dense=True,
    )

    quality_slider = ft.Slider(
        min=1, max=100, value=85, divisions=99,
        label="{value}%", width=180,
    )
    quality_label = ft.Text("85%", size=13, color=COLORS["accent"])

    size_field = ft.TextField(
        label="Макс. px", hint_text="0 = ориг.",
        value="0", width=110, dense=True,
        keyboard_type=ft.KeyboardType.NUMBER,
    )

    def on_quality_change(e):
        quality_label.value = f"{int(e.control.value)}%"
        page.update()

    quality_slider.on_change = on_quality_change

    # ── Конвертация ───────────────────────────────────────────────────────

    progress_bar = ft.ProgressBar(
        width=0, height=6, color=COLORS["accent"],
        bgcolor=COLORS["surface"],
    )
    status_main = ft.Text("Ожидание файлов...", size=14, color=COLORS["text2"])
    status_sub = ft.Text("", size=12, color=COLORS["text3"])

    convert_btn = ft.ElevatedButton(
        "⚡ Конвертировать",
        icon=ft.icons.PLAY_ARROW_ROUNDED,
        style=ft.ButtonStyle(
            bgcolor=COLORS["accent"], color=COLORS["bg"],
            shape=ft.RoundedRectangleBorder(radius=10),
        ),
        disabled=True,
    )
    clear_btn = ft.OutlinedButton(
        "Очистить",
        icon=ft.icons.DELETE_OUTLINE,
        style=ft.ButtonStyle(color=COLORS["text3"]),
        disabled=True,
    )
    open_btn = ft.OutlinedButton(
        "Открыть папку",
        icon=ft.icons.FOLDER_OPEN,
        style=ft.ButtonStyle(color=COLORS["text3"]),
        visible=False,
    )

    def update_buttons():
        has_files = len(file_entries) > 0
        convert_btn.disabled = not has_files or is_running
        clear_btn.disabled = not has_files or is_running
        page.update()

    def open_output(e):
        out_dir = Path.cwd() / "CONVERTED"
        if out_dir.exists():
            os.system(f'xdg-open "{out_dir}"' if os.name == "posix"
                      else f'start "" "{out_dir}"')

    open_btn.on_click = open_output

    # ── Процесс конвертации ───────────────────────────────────────────────

    def do_convert(e):
        nonlocal is_running, cancel_flag
        if is_running or not file_entries:
            return

        is_running = True
        cancel_flag = False

        # Сброс результатов
        for entry in file_entries:
            entry["result"] = None

        fmt = format_dropdown.value if format_dropdown.value != "auto" else ""
        quality = int(quality_slider.value)
        max_size = int(size_field.value or "0")

        out_dir = Path.cwd() / "CONVERTED"
        out_dir.mkdir(exist_ok=True, parents=True)

        requests = [
            ConvertRequest(
                e["path"], out_dir, output_format=fmt,
                quality=quality, max_size=max_size,
            )
            for e in file_entries
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
        convert_btn.on_click = lambda _: setattr(cancel_flag, "value", True)
        open_btn.visible = False
        update_buttons()
        refresh_file_list()

        def cancel_click(_):
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
                    # Находим entry и обновляем
                    for entry in file_entries:
                        if entry["path"] == req.input_path:
                            entry["result"] = res
                            break
                    done += 1
                    # Обновляем UI из главного потока
                    progress_bar.value = done / total
                    elapsed = time.time() - start_time
                    eta = (elapsed / done * (total - done)) if done > 0 else 0
                    status_main.value = f"⏳ {done}/{total}  ({fmt_time(elapsed)} / ~{fmt_time(eta)})"
                    page.update()
                    refresh_file_list()
            finally:
                is_running = False

            # Итог
            ok = sum(1 for e in file_entries
                     if e.get("result") and e["result"].ok)
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
                status_main.color = COLORS["warning"] if fail > 0 else COLORS["success"]
                open_btn.visible = ok > 0

            total_src = sum(e.get("result").src_size
                           for e in file_entries
                           if e.get("result"))
            total_dst = sum(e.get("result").dst_size
                           for e in file_entries
                           if e.get("result") and e["result"].ok)
            total_time = sum(e.get("result").took
                            for e in file_entries
                            if e.get("result"))
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
    clear_btn.on_click = lambda _: clear_all()

    # ── Layout ─────────────────────────────────────────────────────────────

    # Header
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
        margin=ft.margin.only(bottom=8),
    )

    # Панель параметров
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
        padding=ft.padding.symmetric(horizontal=14, vertical=8),
        border_radius=10,
        bgcolor=COLORS["surface"],
        margin=ft.margin.only(top=6, bottom=6),
    )

    # Статус-бар
    status_bar = ft.Column([
        ft.Row([
            progress_bar,
        ]),
        ft.Row([
            status_main,
            status_sub,
            open_btn,
        ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
    ], spacing=4)

    # Кнопки
    btn_row = ft.Row([
        convert_btn,
        clear_btn,
    ], spacing=10)

    # Сборка
    page.add(
        header,
        drag_target,
        params_panel,
        file_list_view,
        btn_row,
        status_bar,
    )

    page.update()


def main_flet():
    """Точка входа для GUI (console_scripts)."""
    ft.app(target=main)


if __name__ == "__main__":
    main_flet()
