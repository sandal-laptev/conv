"""Панель параметров конвертации (пресет, формат, качество, размер)."""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from conv.core import OUTPUT_FORMATS, QUALITY_PRESETS
from conv.gui.theme import COLORS
from conv.logger import get_logger

log = get_logger("conv.params")


class ParamsPanel(ctk.CTkFrame):
    """Панель с пресетом, форматом, качеством и макс. размером.

    Сигналы:
      on_format_changed()  — формат изменился (нужно обновить список)
    """

    def __init__(self, parent, on_format_changed: Callable | None = None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.grid_columnconfigure((0, 1, 2), weight=1)
        self._on_format_changed = on_format_changed

        # Пресет
        ctk.CTkLabel(self, text="Пресет:", text_color=COLORS["text2"]).grid(
            row=0, column=0, sticky="w")
        preset_options = (
            [f"{v.label} — {v.description}" for v in QUALITY_PRESETS.values()]
            + ["— Кастом"]
        )
        self._preset_var = ctk.StringVar(value=preset_options[1])  # web
        preset_menu = ctk.CTkOptionMenu(
            self, variable=self._preset_var, values=preset_options, width=300,
        )
        preset_menu.grid(row=1, column=0, sticky="w", padx=(0, 10))
        preset_menu.configure(command=self._on_preset_change)

        # Формат
        ctk.CTkLabel(self, text="Формат:", text_color=COLORS["text2"]).grid(
            row=0, column=1, sticky="w")
        fmt_options = ["Авто"] + [f"{k} — {v['desc']}" for k, v in OUTPUT_FORMATS.items()]
        self._fmt_var = ctk.StringVar(value="Авто")
        fmt_menu = ctk.CTkOptionMenu(
            self, variable=self._fmt_var, values=fmt_options, width=160,
        )
        fmt_menu.grid(row=1, column=1, sticky="w", padx=(0, 10))
        fmt_menu.configure(command=self._on_format_selected)

        # Качество
        ctk.CTkLabel(self, text="Качество:", text_color=COLORS["text2"]).grid(
            row=0, column=2, sticky="w")
        self._quality_var = ctk.IntVar(value=80)
        quality_slider = ctk.CTkSlider(
            self, variable=self._quality_var,
            from_=1, to=100, number_of_steps=99, width=160,
        )
        quality_slider.grid(row=1, column=2, sticky="w", padx=(0, 10))
        self._quality_label = ctk.CTkLabel(
            self, text="80%", width=40, text_color=COLORS["accent"],
        )
        self._quality_label.grid(row=1, column=2, sticky="e", padx=(0, 10))
        quality_slider.configure(command=self._on_quality_change)

        # Макс. размер (row 2)
        ctk.CTkLabel(self, text="Макс. px (0 = ориг):",
                     text_color=COLORS["text2"]).grid(row=2, column=1, sticky="w")
        self._size_entry = ctk.CTkEntry(self, width=100, placeholder_text="0")
        self._size_entry.grid(row=2, column=2, sticky="w", padx=(0, 10))
        self._size_entry.insert(0, "1920")
        self._size_entry.bind("<KeyRelease>", self._on_size_changed)

        # Режим: только переименовать (row 3)
        self._rename_var = ctk.BooleanVar(value=False)
        self._rename_cb = ctk.CTkCheckBox(
            self, text="🔄 Только переименовать (без конвертации)",
            variable=self._rename_var,
            command=self._on_rename_toggle,
            text_color=COLORS["text2"],
            font=ctk.CTkFont(size=11),
        )
        self._rename_cb.grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))

    # ── Публичное API ──────────────────────────────────────────────────

    @property
    def format_raw(self) -> str:
        return self._fmt_var.get()

    @property
    def format_name(self) -> str:
        raw = self._fmt_var.get()
        return "" if raw == "Авто" else raw.split(" — ")[0]

    @property
    def quality(self) -> int:
        return self._quality_var.get()

    @quality.setter
    def quality(self, value: int):
        self._quality_var.set(value)
        self._quality_label.configure(text=f"{value}%")

    @property
    def max_size(self) -> int:
        return int(self._size_entry.get() or "0")

    @max_size.setter
    def max_size(self, value: int):
        self._size_entry.delete(0, "end")
        self._size_entry.insert(0, str(value))

    @property
    def rename_only(self) -> bool:
        """True = только переименовать (без конвертации)."""
        return self._rename_var.get()

    # ── Внутреннее ─────────────────────────────────────────────────────

    def _on_quality_change(self, value: float):
        self._quality_label.configure(text=f"{int(value)}%")
        self._unset_preset()

    def _on_size_changed(self, *_):
        self._unset_preset()

    def _unset_preset(self):
        if self._preset_var.get() != "— Кастом":
            self._preset_var.set("— Кастом")

    def _on_preset_change(self, choice: str):
        for p in QUALITY_PRESETS.values():
            if choice.startswith(f"{p.label} — "):
                self.quality = p.quality
                self.max_size = p.max_size
                log.info("Пресет: %s (q=%d, s=%d)", p.label, p.quality, p.max_size)
                return

    def _on_rename_toggle(self):
        """Переключение режима переименования."""
        log.info("Режим переименования: %s", self._rename_var.get())

    def _on_format_selected(self, *_):
        if self._on_format_changed:
            self._on_format_changed()
