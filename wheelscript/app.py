"""Точка входа: логирование, один экземпляр, запуск сервиса и окна."""

from __future__ import annotations

import ctypes
import logging
import sys
from logging.handlers import RotatingFileHandler

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


UI_FONT_SIZE = 10
STYLE = "windows11"  # на Windows 10 Qt сам возьмёт windowsvista
_translators: list = []  # Qt хранит только указатель — держим объект живым


def create_app():
    """QApplication со стилем Windows 11, шрифтом, иконкой и русскими текстами Qt."""
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
    from PySide6.QtGui import QFont, QIcon
    from PySide6.QtWidgets import QApplication, QStyleFactory

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    if STYLE in [k.lower() for k in QStyleFactory.keys()]:
        app.setStyle(STYLE)
    font = QFont(app.font())
    font.setPointSize(UI_FONT_SIZE)
    app.setFont(font)
    icon = storage.resource_path("assets/icon.ico")
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    if not _translators:
        tr = QTranslator(app)
        # стандартные кнопки («Да», «Отмена») и окна выбора файла — из каталога самого Qt
        if tr.load(QLocale(QLocale.Russian), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
            app.installTranslator(tr)
            _translators.append(tr)
    return app


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ["--selftest"]:
        # Без окна, без лога в папке настроек и без проверки второго экземпляра: только
        # сервис ввода на пару секунд, итог - в файл (у оконного exe нет консоли).
        import tempfile
        from pathlib import Path

        from . import selftest
        path = Path(args[1]) if len(args) > 1 else Path(tempfile.gettempdir()) / "WheelScript-selftest.txt"
        sys.exit(selftest.run(path))

    _setup_logging()
    log.info("%s %s starting (portable=%s)", APP_NAME, __version__, storage.is_portable())
    app = create_app()
    from PySide6.QtWidgets import QMessageBox
    if not _single_instance():
        QMessageBox.information(None, APP_NAME, f"{APP_NAME} уже запущен.")
        return

    from .qt.main_window import MainWindow
    from .service import InputService

    cfg, warning = storage.load_config()
    path = storage.config_path()
    try:
        storage.save_config(cfg, path)
    except OSError as e:
        warning = (warning + "\n\n" if warning else "") + f"Не удалось записать настройки: {e}"

    service = InputService(cfg.settings.tick_rate)
    service.start()

    def report(exc, val, tb):
        log.error("UI error", exc_info=(exc, val, tb))
        QMessageBox.critical(None, APP_NAME, f"Ошибка: {val}")

    sys.excepthook = report
    window = MainWindow(service, cfg, path, warning)
    window.show()
    try:
        app.exec()
    finally:
        service.stop()
        log.info("stopped")


if __name__ == "__main__":
    main()
