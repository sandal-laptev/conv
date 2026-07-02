"""conv GUI — CustomTkinter-интерфейс."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox

from conv.core import (
    Converter,
    ConvertRequest,
    ConvertResult,
    OUTPUT_FORMATS,
    VIDEO_INPUT,
    AUDIO_INPUT,
    ALL_INPUT,
)
from conv.logger import get_logger, tail as log_tail, log_path as log_file_path

log = get_logger("conv.gui")

# ── Цветовая схема ───────────────────────────────────────────────────────────

COLORS = {
    "bg": "#0a0a2e",
    "surface": "#1a1a3e",
    "surface2": "#252550",
    "accent": "#00d4ff",
    "accent2": "#7b2ff7",
    "success": "#00e676",
    "error": "#ff1744",
    "text": "#e0e0e0",
    "text2": "#9e9e9e",
}

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ── Хелперы ──────────────────────────────────────────────────────────────────

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


# ── Главное окно ─────────────────────────────────────────────────────────────

class ConvApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("🖧 conv — Иохим Кузьмич Media Converter")
        self.geometry("880x720")
        self.minsize(700, 600)

        # Состояние
        self.converter = Converter()
        self.file_paths: list[Path] = []
        self.file_results: dict[Path, ConvertResult] = {}
        self.is_running = False
        self.cancel_flag = False

        self._build_ui()
        log.info("GUI запущен (CustomTkinter)")

    # ── Сборка интерфейса ───────────────────────────────────────────────

    def _build_ui(self):
        # Сетка
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)  # список файлов тянется

        # ── Заголовок ──
        header = ctk.CTkLabel(
            self, text="🖧  conv  —  Иохим Кузьмич Media Converter",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["accent"],
        )
        header.grid(row=0, column=0, pady=(15, 5), padx=15, sticky="w")

        # ── Зона drag'n'drop / выбора файлов ──
        self.drop_frame = ctk.CTkFrame(self, height=100,
                                        fg_color=COLORS["surface"],
                                        border_color=COLORS["accent"],
                                        border_width=2)
        self.drop_frame.grid(row=1, column=0, pady=5, padx=15, sticky="ew")
        self.drop_frame.grid_propagate(False)

        self.drop_label = ctk.CTkLabel(
            self.drop_frame,
            text="📁  Нажмите для выбора файлов  (или перетащите сюда)",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text2"],
        )
        self.drop_label.place(relx=0.5, rely=0.5, anchor="center")

        # drag'n'drop через tkinterdnd2
        try:
            self.drop_frame.drop_target_register(".*")
            self.drop_frame.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            log.warning("DnD не поддерживается на этой платформе")

        self.drop_frame.bind("<Button-1>", self._pick_files)
        self.drop_label.bind("<Button-1>", self._pick_files)

        # ── Параметры ──
        params_frame = ctk.CTkFrame(self, fg_color="transparent")
        params_frame.grid(row=2, column=0, pady=(5, 0), padx=15, sticky="ew")
        params_frame.grid_columnconfigure((0, 1, 2), weight=1)

        # Формат
        fmt_options = ["Авто"] + [f"{k} — {v['desc']}" for k, v in OUTPUT_FORMATS.items()]
        self.fmt_var = ctk.StringVar(value="Авто")
        ctk.CTkLabel(params_frame, text="Формат:", text_color=COLORS["text2"]).grid(
            row=0, column=0, sticky="w")
        fmt_menu = ctk.CTkOptionMenu(params_frame, variable=self.fmt_var,
                                       values=fmt_options, width=160)
        fmt_menu.grid(row=1, column=0, sticky="w", padx=(0, 10))

        # Качество
        ctk.CTkLabel(params_frame, text="Качество:", text_color=COLORS["text2"]).grid(
            row=0, column=1, sticky="w")
        self.quality_var = ctk.IntVar(value=85)
        quality_slider = ctk.CTkSlider(params_frame, variable=self.quality_var,
                                        from_=1, to=100, number_of_steps=99, width=160)
        quality_slider.grid(row=1, column=1, sticky="w", padx=(0, 10))
        self.quality_label = ctk.CTkLabel(params_frame, text="85%", width=40,
                                           text_color=COLORS["accent"])
        self.quality_label.grid(row=1, column=1, sticky="e", padx=(0, 10))
        quality_slider.configure(command=self._on_quality_change)

        # Макс. размер
        ctk.CTkLabel(params_frame, text="Макс. px (0 = ориг):",
                     text_color=COLORS["text2"]).grid(row=0, column=2, sticky="w")
        self.size_entry = ctk.CTkEntry(params_frame, width=100, placeholder_text="0")
        self.size_entry.grid(row=1, column=2, sticky="w")
        self.size_entry.insert(0, "0")

        # ── Список файлов (скроллируемый) ──
        list_frame = ctk.CTkFrame(self, fg_color="transparent")
        list_frame.grid(row=3, column=0, pady=5, padx=15, sticky="nsew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

        self.file_textbox = ctk.CTkTextbox(list_frame, font=ctk.CTkFont(size=12),
                                            fg_color=COLORS["surface"],
                                            text_color=COLORS["text"])
        self.file_textbox.grid(row=0, column=0, sticky="nsew")
        self.file_textbox.configure(state="disabled")

        # ── Кнопки ──
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=4, column=0, pady=(5, 0), padx=15, sticky="ew")
        btn_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=0)

        self.convert_btn = ctk.CTkButton(btn_frame, text="⚡ Конвертировать",
                                          fg_color=COLORS["accent"],
                                          text_color=COLORS["bg"],
                                          hover_color="#00b8e6",
                                          command=self._do_convert,
                                          state="disabled")
        self.convert_btn.grid(row=0, column=0, padx=(0, 8))

        self.clear_btn = ctk.CTkButton(btn_frame, text="🗑 Очистить",
                                        fg_color=COLORS["surface2"],
                                        text_color=COLORS["text2"],
                                        command=self._clear_all,
                                        state="disabled")
        self.clear_btn.grid(row=0, column=1, padx=(0, 8))

        self.open_btn = ctk.CTkButton(btn_frame, text="📂 Открыть",
                                       fg_color=COLORS["surface2"],
                                       text_color=COLORS["text2"],
                                       command=self._open_output,
                                       state="disabled")
        self.open_btn.grid(row=0, column=2, padx=(0, 8))

        self.log_btn = ctk.CTkButton(btn_frame, text="📋 Логи",
                                      fg_color=COLORS["surface2"],
                                      text_color=COLORS["text2"],
                                      command=self._copy_logs)
        self.log_btn.grid(row=0, column=3, padx=(0, 8))

        self.clear_btn = ctk.CTkButton(btn_frame, text="✕ Закрыть",
                                        fg_color=COLORS["surface2"],
                                        text_color=COLORS["text2"],
                                        command=self.destroy)
        self.clear_btn.grid(row=0, column=4)

        # ── Прогресс и статус ──
        status_frame = ctk.CTkFrame(self, fg_color="transparent")
        status_frame.grid(row=5, column=0, pady=(5, 15), padx=15, sticky="ew")
        status_frame.grid_columnconfigure(1, weight=1)

        self.progress_bar = ctk.CTkProgressBar(status_frame, width=400,
                                                fg_color=COLORS["surface"],
                                                progress_color=COLORS["accent"])
        self.progress_bar.grid(row=0, column=0, columnspan=2, pady=(0, 4), sticky="ew")
        self.progress_bar.set(0)

        self.status_var = ctk.StringVar(value="Ожидание файлов...")
        self.status_label = ctk.CTkLabel(status_frame, textvariable=self.status_var,
                                          text_color=COLORS["text2"], anchor="w")
        self.status_label.grid(row=1, column=0, sticky="w")

        self.stats_var = ctk.StringVar(value="")
        self.stats_label = ctk.CTkLabel(status_frame, textvariable=self.stats_var,
                                         text_color=COLORS["text3"], anchor="e")
        self.stats_label.grid(row=1, column=1, sticky="e")

        log.debug("UI построен")

    # ── Качество ──

    def _on_quality_change(self, value):
        self.quality_label.configure(text=f"{int(value)}%")

    # ── Выбор файлов ──

    def _pick_files(self, event=None):
        if self.is_running:
            return
        files = filedialog.askopenfiles(
            title="Выберите медиафайлы",
            multiple=True,
            filetypes=[("Медиафайлы",
                        " ".join(f"*{e}" for e in sorted(ALL_INPUT))),
                       ("Все файлы", "*.*")],
        )
        if files:
            paths = []
            for f in files:
                p = Path(f.name)
                if p.suffix.lower() in ALL_INPUT:
                    paths.append(p)
                    log.debug("Выбран файл: %s", p.name)
            self._add_files(paths)
            log.info("Выбрано файлов: %d", len(paths))

    def _on_drop(self, event):
        if self.is_running:
            return
        raw = event.data.strip()
        paths = []
        for line in raw.split("\r\n") if "\r\n" in raw else raw.split("\n"):
            line = line.strip().strip("{").strip("}")
            if line:
                p = Path(line)
                if p.exists() and p.suffix.lower() in ALL_INPUT:
                    paths.append(p)
        if paths:
            self._add_files(paths)
            log.info("Дропнуто файлов: %d", len(paths))

    # ── Управление списком файлов ──

    def _add_files(self, paths: list[Path]):
        existing = set(self.file_paths)
        for p in paths:
            if p not in existing:
                self.file_paths.append(p)
                existing.add(p)
        self._refresh_file_list()
        self._update_buttons()

    def _remove_file(self, path: Path):
        if self.is_running:
            return
        if path in self.file_paths:
            self.file_paths.remove(path)
            self.file_results.pop(path, None)
        self._refresh_file_list()
        self._update_buttons()

    def _clear_all(self):
        if self.is_running:
            return
        self.file_paths.clear()
        self.file_results.clear()
        self._refresh_file_list()
        self._update_buttons()
        self.status_var.set("Ожидание файлов...")
        self.stats_var.set("")
        self.progress_bar.set(0)
        log.info("Список очищен")

    def _refresh_file_list(self):
        self.file_textbox.configure(state="normal")
        self.file_textbox.delete("0.0", "end")

        if not self.file_paths:
            self.file_textbox.insert("0.0", "  (нет файлов — нажмите на область выше для выбора)\n")
        else:
            # Заголовок
            header = f"  {'📄 Файл':<50} {'Размер':>8} {'Статус':>10} {'Результат':<25}\n"
            header += f"  {'─'*50} {'─'*8} {'─'*10} {'─'*25}\n"
            self.file_textbox.insert("end", header)

            for p in self.file_paths:
                ext = p.suffix.lower()
                sym = "🎬" if ext in VIDEO_INPUT else "🎵" if ext in AUDIO_INPUT else "🖼"
                name = f"{sym} {p.name}"
                size_str = fmt_size(_size(p))

                res = self.file_results.get(p)
                if res and res.ok:
                    status = "✅ OK"
                    info = f"{fmt_size(res.dst_size)} ({res.dst_size / res.src_size * 100:.0f}%) — {res.fmt_took()}" if res.src_size > 0 else "done"
                elif res and not res.ok:
                    status = "❌ ERR"
                    info = res.error[:40]
                else:
                    status = "⏳"
                    info = ""

                line = f"  {name:<48} {size_str:>8} {status:>10} {info:<25}\n"
                self.file_textbox.insert("end", line)

        self.file_textbox.configure(state="disabled")

    def _update_buttons(self):
        has_files = len(self.file_paths) > 0
        self.convert_btn.configure(state="normal" if has_files and not self.is_running else "disabled")
        self.clear_btn.configure(state="normal" if has_files and not self.is_running else "disabled")

    # ── Конвертация ──

    def _do_convert(self):
        if self.is_running or not self.file_paths:
            return

        self.is_running = True
        self.cancel_flag = False
        self.file_results.clear()

        # Парсим формат
        fmt_raw = self.fmt_var.get()
        fmt = ""
        if fmt_raw != "Авто":
            fmt = fmt_raw.split(" — ")[0]

        quality = self.quality_var.get()
        max_size = int(self.size_entry.get() or "0")

        out_dir = Path.cwd() / "CONVERTED"
        out_dir.mkdir(exist_ok=True, parents=True)

        requests = [
            ConvertRequest(p, out_dir, output_format=fmt,
                           quality=quality, max_size=max_size)
            for p in self.file_paths
        ]

        total = len(requests)
        done = 0
        start = time.time()

        self.status_var.set("⏳ Конвертация...")
        self.progress_bar.set(0)
        self.convert_btn.configure(text="⏹ Отмена", fg_color=COLORS["error"],
                                   command=self._cancel_convert)
        self.open_btn.configure(state="disabled")
        self._update_buttons()
        self._refresh_file_list()

        def run():
            nonlocal done
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                for req in requests:
                    if self.cancel_flag:
                        break
                    res = self.converter.convert_one(req)
                    self.file_results[req.input_path] = res
                    done += 1

                    elapsed = time.time() - start
                    eta = (elapsed / done * (total - done)) if done > 0 else 0
                    self._ui_thread(lambda: self._update_progress(done, total, elapsed, eta))
                loop.close()
            except Exception as ex:
                log.exception("Ошибка в потоке конвертации")
                self._ui_thread(lambda: self.status_var.set(f"❌ {ex}"))
            finally:
                self.is_running = False
                self._ui_thread(self._finish_convert)

        threading.Thread(target=run, daemon=True).start()
        log.info("Конвертация запущена: %d файлов", total)

    def _cancel_convert(self):
        self.cancel_flag = True
        log.info("Конвертация отменена пользователем")

    def _update_progress(self, done, total, elapsed, eta):
        self.progress_bar.set(done / total)
        self.status_var.set(f"⏳ {done}/{total}  ({fmt_time(elapsed)} / ~{fmt_time(eta)})")
        self._refresh_file_list()

    def _finish_convert(self):
        ok = sum(1 for p in self.file_paths if self.file_results.get(p) and self.file_results[p].ok)
        total = len(self.file_paths)
        fail = total - ok

        if self.cancel_flag and ok == 0:
            self.status_var.set("⏹ Отменено")
        elif fail == 0:
            self.status_var.set(f"✅ Готово: {ok}/{total}")
            self.open_btn.configure(state="normal")
        else:
            self.status_var.set(f"✅ {ok}/{total}  ❌ {fail}/{total}")
            if ok > 0:
                self.open_btn.configure(state="normal")

        total_src = sum(self.file_results[p].src_size for p in self.file_paths if self.file_results.get(p))
        total_dst = sum(self.file_results[p].dst_size for p in self.file_paths
                        if self.file_results.get(p) and self.file_results[p].ok)
        total_time = sum(self.file_results[p].took for p in self.file_paths if self.file_results.get(p))
        if total_src > 0:
            pct = total_dst / total_src * 100 if total_dst > 0 else 0
            self.stats_var.set(f"📦 {fmt_size(total_src)} → {fmt_size(total_dst)} ({pct:.0f}%)  ⏱ {fmt_time(total_time)}")

        self.progress_bar.set(1.0)
        self.convert_btn.configure(text="⚡ Конвертировать", fg_color=COLORS["accent"],
                                   command=self._do_convert)
        self._update_buttons()
        self._refresh_file_list()
        log.info("Конвертация завершена: %d/%d успешно", ok, total)

    def _ui_thread(self, func):
        """Запускает функцию в главном потоке (thread-safe update)."""
        self.after(0, func)

    # ── Открыть папку ──

    def _open_output(self):
        out_dir = Path.cwd() / "CONVERTED"
        if out_dir.exists():
            if os.name == "posix":
                os.system(f'xdg-open "{out_dir}"')
            else:
                os.system(f'start "" "{out_dir}"')

    # ── Копировать логи ──

    def _copy_logs(self):
        lines = log_tail(80)
        self.clipboard_clear()
        self.clipboard_append(lines)
        # Обратная связь
        orig = self.log_btn.cget("text")
        self.log_btn.configure(text="✅ Скопировано!")
        threading.Timer(2.0, lambda: self.after(0, lambda: self.log_btn.configure(text=orig))).start()
        log.info("Логи скопированы в буфер (%d строк)", len(lines.split("\n")) - 1)


def _size(p: Path) -> int:
    try:
        return p.stat().st_size
    except OSError:
        return 0


# ── Точка входа ──────────────────────────────────────────────────────────────

def main_flet():
    """Заглушка для совместимости со старыми entry points."""
    run_gui()


def run_gui():
    app = ConvApp()
    app.mainloop()


if __name__ == "__main__":
    run_gui()
