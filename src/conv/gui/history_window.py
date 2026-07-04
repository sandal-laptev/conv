"""Окно истории конвертаций (CTkToplevel)."""

from __future__ import annotations

import time
from pathlib import Path

import customtkinter as ctk

from conv.gui.theme import COLORS, fmt_size, fmt_time
from conv.history import HistoryManager
from conv.logger import get_logger

log = get_logger("conv.history_gui")


class HistoryWindow(ctk.CTkToplevel):
    """Окно с лентой последних конвертаций."""

    def __init__(self, parent, history: HistoryManager, **kwargs):
        super().__init__(parent, **kwargs)
        self.title("📜 История конвертаций — conv")
        self.geometry("700x400")
        self.minsize(500, 250)

        self._history = history

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Заголовок
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, pady=(10, 4), padx=12, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header, text="📜 История конвертаций",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=COLORS["accent"],
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            header, text="🗑 Очистить", width=100,
            fg_color=COLORS["surface2"], text_color=COLORS["text2"],
            command=self._clear_history,
        ).grid(row=0, column=1, padx=4)

        ctk.CTkButton(
            header, text="✕ Закрыть", width=80,
            fg_color=COLORS["surface2"], text_color=COLORS["text2"],
            command=self.destroy,
        ).grid(row=0, column=2, padx=4)

        # Текстовая область с историей
        self._textbox = ctk.CTkTextbox(
            self, font=ctk.CTkFont(size=12),
            fg_color=COLORS["surface"], text_color=COLORS["text"],
        )
        self._textbox.grid(row=1, column=0, pady=(0, 10), padx=12, sticky="nsew")
        self._textbox.configure(state="disabled")

        self._rebuild()

    def _rebuild(self):
        """Построить/обновить содержимое."""
        entries = self._history.get_all()
        self._textbox.configure(state="normal")
        self._textbox.delete("0.0", "end")

        if not entries:
            self._textbox.insert(
                "0.0",
                "  (пусто — пока нет завершённых конвертаций)\n",
            )
        else:
            header = (
                f"  {'#':<3} {'Операция':<16} {'Файл':<28}"
                f" {'Результат':<20} {'Размер':<14} {'Время':<10}\n"
            )
            header += (
                f"  {'─'*3} {'─'*16} {'─'*28} {'─'*20} {'─'*14} {'─'*10}\n"
            )
            self._textbox.insert("end", header)

            for i, e in enumerate(entries, 1):
                line = self._format_entry(i, e)
                self._textbox.insert("end", line)

        self._textbox.configure(state="disabled")

    def _format_entry(self, idx: int, e: dict) -> str:
        sym = "✅" if e.get("ok") else "❌"
        op = e.get("operation", "?")
        inp = e.get("input_name", "?")
        out = e.get("output_name", "?") or "—"
        src_s = e.get("src_size", 0)
        dst_s = e.get("dst_size", 0)
        ratio = f"{dst_s / src_s * 100:.0f}%" if src_s > 0 else ""
        took = e.get("took", 0)
        when = e.get("timestamp", 0)

        # Относительное время
        age = ""
        if when:
            delta = time.time() - when
            if delta < 60:
                age = "только что"
            elif delta < 3600:
                age = f"{int(delta // 60)}м назад"
            elif delta < 86400:
                age = f"{int(delta // 3600)}ч назад"
            else:
                age = f"{int(delta // 86400)}д назад"

        err = e.get("error", "")
        info = f"{fmt_size(src_s)}→{fmt_size(dst_s)} {ratio}" if ratio else fmt_size(src_s)
        if err:
            info = f"❌ {err[:30]}"

        return (
            f"  {idx:<3} {sym} {op:<12} {inp:<28}"
            f" {out:<20} {info:<14} {age:<10}\n"
        )

    def _clear_history(self):
        self._history.clear()
        self._rebuild()
        log.info("История очищена")
