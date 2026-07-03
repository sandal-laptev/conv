"""Управление конвертацией: запуск, прогресс, отмена."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

from conv.core import Converter, ConvertRequest, ConvertResult
from conv.logger import get_logger

log = get_logger("conv.controller")


class ConversionController:
    """Потокобезопасный контроллер конвертации.

    Сигналы (вызываются в главном потоке через callback):
      on_progress(done, total, elapsed, eta)
      on_finish(results: list[ConvertResult], cancelled: bool)
    """

    def __init__(
        self,
        converter: Converter | None = None,
        on_progress: Callable | None = None,
        on_finish: Callable | None = None,
    ):
        self.converter = converter or Converter()
        self._on_progress = on_progress
        self._on_finish = on_finish
        self.is_running = False
        self._cancel_flag = False

    @property
    def cancelled(self) -> bool:
        return self._cancel_flag

    def cancel(self):
        """Запросить отмену конвертации."""
        self._cancel_flag = True
        log.info("Конвертация отменена пользователем")

    def start(self, requests: list[ConvertRequest]):
        """Запустить конвертацию в фоновом потоке."""
        if self.is_running:
            return

        self.is_running = True
        self._cancel_flag = False
        total = len(requests)

        log.info("Конвертация запущена: %d файлов", total)

        def run():
            results: list[ConvertResult] = []
            done = 0
            start = time.time()

            try:
                for req in requests:
                    if self._cancel_flag:
                        break
                    res = self.converter.convert_one(req)
                    results.append(res)
                    done += 1

                    elapsed = time.time() - start
                    eta = (elapsed / done * (total - done)) if done > 0 else 0

                    if self._on_progress:
                        self._on_progress(done, total, elapsed, eta)
            except Exception as ex:
                log.exception("Ошибка в потоке конвертации")
            finally:
                self.is_running = False
                cancelled = self._cancel_flag
                if self._on_finish:
                    self._on_finish(results, cancelled)

        threading.Thread(target=run, daemon=True).start()
