"""Зона выбора файлов (диалог + drag'n'drop)."""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from conv.core import ALL_INPUT
from conv.gui.theme import COLORS
from conv.logger import get_logger

log = get_logger("conv.drop_zone")


class DropZone(ctk.CTkFrame):
    """Область для выбора файлов (клик) и drag'n'drop.

    Сигналы:
      on_files_selected(paths: list[Path])
    """

    def __init__(self, parent, on_files_selected: Callable | None = None, **kwargs):
        super().__init__(parent, height=100,
                         fg_color=COLORS["surface"],
                         border_color=COLORS["accent"],
                         border_width=2, **kwargs)
        self.grid_propagate(False)
        self._callback = on_files_selected

        self.label = ctk.CTkLabel(
            self,
            text="📁  Нажмите для выбора файлов  (или перетащите сюда)",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text2"],
        )
        self.label.place(relx=0.5, rely=0.5, anchor="center")

        # drag'n'drop (tkinterdnd2)
        try:
            self.drop_target_register(".*")
            self.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            log.warning("DnD не поддерживается на этой платформе")

        self.bind("<Button-1>", self._pick_files)
        self.label.bind("<Button-1>", self._pick_files)

    def _pick_files(self, event=None):
        files = filedialog.askopenfiles(
            title="Выберите медиафайлы",
            multiple=True,
            filetypes=[
                ("Медиафайлы", " ".join(f"*{e}" for e in sorted(ALL_INPUT))),
                ("Все файлы", "*.*"),
            ],
        )
        if files:
            paths = []
            for f in files:
                p = Path(f.name)
                if p.suffix.lower() in ALL_INPUT:
                    paths.append(p)
                    log.debug("Выбран файл: %s", p.name)
            if paths and self._callback:
                self._callback(paths)
            log.info("Выбрано файлов: %d", len(paths))

    def _on_drop(self, event):
        raw = event.data.strip()
        paths = []
        for line in raw.split("\r\n") if "\r\n" in raw else raw.split("\n"):
            line = line.strip().strip("{").strip("}")
            if line:
                p = Path(line)
                if p.exists() and p.suffix.lower() in ALL_INPUT:
                    paths.append(p)
        if paths and self._callback:
            self._callback(paths)
            log.info("Дропнуто файлов: %d", len(paths))
