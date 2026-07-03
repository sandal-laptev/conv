"""Виджет списка файлов с колонками и статусами."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import customtkinter as ctk

from conv.core import (
    AUDIO_INPUT,
    VIDEO_INPUT,
    ConvertResult,
    resolve_format as resolve_fmt,
)
from conv.gui.theme import COLORS, file_size, fmt_size
from conv.logger import get_logger

log = get_logger("conv.file_list")


class FileList(ctk.CTkFrame):
    """Список файлов с колонками: имя → формат размер статус результат.

    Сигналы:
      on_file_click(idx: int)  — клик по строке файла
    """

    def __init__(
        self,
        parent,
        on_file_click: Callable | None = None,
        **kwargs,
    ):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._on_file_click = on_file_click
        self._paths: list[Path] = []
        self._results: dict[Path, ConvertResult] = {}
        self._target_format: str = ""  # пусто = авто

        self._textbox = ctk.CTkTextbox(
            self, font=ctk.CTkFont(size=12),
            fg_color=COLORS["surface"], text_color=COLORS["text"],
        )
        self._textbox.grid(row=0, column=0, sticky="nsew")
        self._textbox.configure(state="disabled")

        if on_file_click:
            self._textbox.bind("<Button-1>", self._on_click)

    # ── Публичное API ──────────────────────────────────────────────────

    @property
    def paths(self) -> list[Path]:
        return self._paths.copy()

    @property
    def count(self) -> int:
        return len(self._paths)

    @property
    def results(self) -> dict[Path, ConvertResult]:
        return self._results

    def set_files(self, paths: list[Path]):
        """Установить список файлов (заменяет текущий)."""
        self._paths = list(paths)
        self._rebuild()

    def add_files(self, paths: list[Path]):
        """Добавить файлы в конец списка."""
        existing = set(self._paths)
        for p in paths:
            if p not in existing:
                self._paths.append(p)
                existing.add(p)
        self._rebuild()

    def remove_file(self, path: Path):
        if path in self._paths:
            self._paths.remove(path)
            self._results.pop(path, None)
        self._rebuild()

    def clear(self):
        self._paths.clear()
        self._results.clear()
        self._rebuild()

    def set_format(self, format_name: str):
        """Установить текущий целевой формат (пусто = авто)."""
        self._target_format = format_name
        self._rebuild()

    def set_result(self, path: Path, result: ConvertResult):
        self._results[path] = result
        self._rebuild()

    def set_results(self, results: dict[Path, ConvertResult]):
        self._results.update(results)
        self._rebuild()

    def reset_results(self):
        self._results.clear()
        self._rebuild()

    # ── Построение списка ──────────────────────────────────────────────

    def _rebuild(self):
        self._textbox.configure(state="normal")
        self._textbox.delete("0.0", "end")

        if not self._paths:
            self._textbox.insert(
                "0.0",
                "  (нет файлов — нажмите на область выше для выбора)\n",
            )
        else:
            header = (
                f"  {'📄 Файл':<42} {'→ формат':>10}"
                f" {'Размер':>8} {'Статус':>10} {'Результат':<25}\n"
            )
            header += (
                f"  {'─'*42} {'─'*10} {'─'*8} {'─'*10} {'─'*25}\n"
            )
            self._textbox.insert("end", header)

            for p in self._paths:
                line = self._format_line(p)
                self._textbox.insert("end", line)

        self._textbox.configure(state="disabled")

    def _format_line(self, path: Path) -> str:
        ext = path.suffix.lower()
        sym = (
            "🎬" if ext in VIDEO_INPUT
            else "🎵" if ext in AUDIO_INPUT
            else "🖼"
        )
        name = f"{sym} {path.name}"

        # Целевой формат
        target_fmt = self._target_format or resolve_fmt("", ext)
        fmt_str = f".{target_fmt}"

        size_str = fmt_size(file_size(path))

        res = self._results.get(path)
        if res and res.ok:
            status = "✅ OK"
            info = (
                f"{fmt_size(res.dst_size)} "
                f"({res.dst_size / res.src_size * 100:.0f}%)"
                f" — {res.fmt_took()}"
                if res.src_size > 0
                else "done"
            )
        elif res and not res.ok:
            status = "❌ ERR"
            info = res.error[:40]
        else:
            status = "⏳"
            info = ""

        return (
            f"  {name:<40} {fmt_str:>10} {size_str:>8}"
            f" {status:>10} {info:<25}\n"
        )

    # ── Клик ──

    def _on_click(self, event):
        if not self._paths or not self._on_file_click:
            return
        y = int(event.y / 18) - 1
        if 0 <= y < len(self._paths):
            self._on_file_click(y)
