"""
Самопроверка собранной программы: WheelScript.exe --selftest [файл].

Поднимает сервис ввода без окна на пару секунд и пишет в файл, что увидела SDL:
версию и путь SDL2.dll, устройства, вибромотор, ошибки. Окно не открывается, клавиши,
мышь, виртуальный геймпад и вибрация не трогаются: маппинг на паузе, горячая клавиша
выключена, профиль не задан. Код возврата 0 - SDL поднялась и сервис не сообщил ошибок.
"""

from __future__ import annotations

import logging
import platform
import queue
import sys
import time
from pathlib import Path

from . import APP_NAME, __version__, sdlinput


class _Collect(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.lines: list[str] = []
        self.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


def run(path: Path, seconds: float = 2.0) -> int:
    from .service import InputService

    root = logging.getLogger()
    collect = _Collect()
    root.addHandler(collect)
    old_level = root.level
    root.setLevel(logging.INFO)
    errors: list[str] = []
    rumble = ""
    devices: list = []
    sdl_text = "?"
    try:
        service = InputService()
        service.suspend()             # маппинг на паузе с первого тика
        service.set_toggle_key("")    # и F8 его не включит
        service.start()
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                kind, value = service.events.get(timeout=0.05)
            except queue.Empty:
                continue
            if kind == "error":
                errors.append(str(value))
            elif kind == "rumble_status":
                rumble = value
            elif kind == "devices":
                devices = list(value)
        service.stop()
        if service._input is not None:
            sdl_text = sdlinput.describe(service._input.sdl)
        if service._thread.is_alive():
            errors.append("поток ввода не остановился")
    except Exception as e:  # noqa: BLE001
        errors.append(f"{type(e).__name__}: {e}")
    finally:
        root.removeHandler(collect)
        root.setLevel(old_level)

    ok = not errors
    lines = [
        f"{APP_NAME} {__version__} selftest",
        f"python: {platform.python_version()} frozen: {'yes' if getattr(sys, 'frozen', False) else 'no'}",
        f"sdl: {sdl_text}",
        f"devices: {len(devices)}",
        *(f"  {d.name} | guid {d.key} | axes {d.axes} | buttons {d.buttons} | hats {d.hats}" for d in devices),
        f"rumble: {rumble}",
        "errors: " + ("; ".join(errors) if errors else "none"),
        f"result: {'OK' if ok else 'FAIL'}",
        "--- log ---",
        *collect.lines,
    ]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1
