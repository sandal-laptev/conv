"""QThread-контроллер для фоновой конвертации."""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot

from conv.core import Converter, ConvertRequest, ConvertResult
from conv.logger import get_logger

log = get_logger("conv.gui_qt.conversion")


class ConversionWorker(QObject):
    """Работает в отдельном QThread; не блокирует GUI.

    Сигналы:
      progress(done: int, total: int, elapsed: float, eta: float)
      file_done(result: ConvertResult)
      finished(results: list[ConvertResult], cancelled: bool)
    """

    progress = Signal(int, int, float, float)   # done, total, elapsed, eta
    file_done = Signal(object)                   # ConvertResult
    finished = Signal(object, bool)              # list[ConvertResult], cancelled

    def __init__(self, converter: Converter, requests: list[ConvertRequest]):
        super().__init__()
        self.converter = converter
        self.requests = requests
        self._cancel_flag = False

    def cancel(self) -> None:
        self._cancel_flag = True

    @Slot()
    def run(self) -> None:
        """Запустить конвертацию. Вызывается из QThread.started."""
        results: list[ConvertResult] = []
        done = 0
        start = time.time()
        total = len(self.requests)

        log.info("Конвертация запущена: %d файлов", total)

        for req in self.requests:
            if self._cancel_flag:
                log.info("Конвертация отменена (%d/%d)", done, total)
                break
            res = self.converter.convert_one(req)
            results.append(res)
            done += 1
            elapsed = time.time() - start
            eta = (elapsed / done * (total - done)) if done > 0 else 0
            self.progress.emit(done, total, elapsed, eta)
            self.file_done.emit(res)

        cancelled = self._cancel_flag
        ok = sum(1 for r in results if r.ok)
        log.info("Конвертация завершена: %d/%d успешно (отмена=%s)", ok, total, cancelled)
        self.finished.emit(results, cancelled)
