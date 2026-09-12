"""Точка входа: логирование, один экземпляр, запуск сервиса и окна."""

from __future__ import annotations

import ctypes
import logging
import sys
import tkinter as tk
from logging.handlers import RotatingFileHandler
from tkinter import messagebox

from . import APP_NAME, __version__, storage

log = logging.getLogger("wheelscript")
_mutex = None


def _setup_logging() -> None:
    handlers: list[logging.Handler] = []
    try:
        d = storage.data_dir()
        d.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(d / "wheelscript.log", maxBytes=1_000_000, backupCount=2,
                                            encoding="utf-8"))
    except OSError:
        pass
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _dpi_aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass


def _single_instance() -> bool:
    """Два экземпляра слали бы ввод дважды — второй не запускаем."""
    global _mutex
    if sys.platform != "win32":
        return True
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = wintypes.HANDLE
    k32.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    _mutex = k32.CreateMutexW(None, False, "Local\\WheelScript.SingleInstance")
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


def main() -> None:
    _setup_logging()
    log.info("%s %s starting (portable=%s)", APP_NAME, __version__, storage.is_portable())
    _dpi_aware()
    if not _single_instance():
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(APP_NAME, f"{APP_NAME} уже запущен.")
        root.destroy()
        return

    from .gui import App
    from .service import InputService

    cfg, warning = storage.load_config()
    path = storage.config_path()
    try:
        storage.save_config(cfg, path)
    except OSError as e:
        warning = (warning + "\n\n" if warning else "") + f"Не удалось записать настройки: {e}"

    service = InputService(cfg.settings.tick_rate)
    service.start()
    root = tk.Tk()
    try:
        root.iconbitmap(default=str(storage.resource_path("assets/icon.ico")))
    except tk.TclError:
        pass

    def report(exc, val, tb):
        log.error("UI error", exc_info=(exc, val, tb))
        messagebox.showerror(APP_NAME, f"Ошибка: {val}", parent=root)

    root.report_callback_exception = report
    App(root, service, cfg, path, warning)
    try:
        root.mainloop()
    finally:
        service.stop()
        log.info("stopped")


if __name__ == "__main__":
    main()
