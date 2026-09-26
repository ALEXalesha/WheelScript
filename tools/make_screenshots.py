r"""Снимки окна для README: собираются программой, а не руками.

    .venv\Scripts\python.exe tools\make_screenshots.py

Окно настоящее: тот же MainWindow, тот же BindingDialog, те же темы. Снимается
оно через QWidget.grab(), а не съёмкой экрана: окно может оказаться позади
других, и в кадр попадёт чужое содержимое.

Подставлен только руль. Физически он к машине сборки не подключён, а без
устройства окно честно пишет «Руль не найден» - и на снимке не было бы видно
ничего из того, ради чего программу и открывают. Поэтому сервис ввода заменён
заглушкой, которая отвечает как подключённый PXN V9 Gen 2 в покое: оси в нуле,
кнопки отпущены. Никакие значения при этом не выдумываются - живых подсветок в
кадре нет, потому что руль никто не трогает.

Настройки уводятся во временную папку: настоящий %APPDATA%\WheelScript не
меняется.
"""

import os
import queue
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
sys.path.insert(0, str(ROOT))


class Руль:
    """Сервис ввода, отвечающий как подключённый руль в покое.

    Ровно те методы, которые зовёт окно: настоящий InputService крутит поток
    опроса SDL, а тут крутить нечего - устройства нет.
    """

    KEY = "wheel"

    def __init__(self):
        self.events = queue.SimpleQueue()
        self.enabled = False

    def snapshot(self):
        from wheelscript.engine import DeviceState
        from wheelscript.service import DeviceInfo

        покой = DeviceState((0.0, None, -1.0, None, None, -1.0, -1.0), (False,) * 12, ((0, 0),))
        return {self.KEY: покой}, [DeviceInfo(self.KEY, "PXN V9 Gen 2", 7, 12, 1)]

    def device_names(self):
        return {self.KEY: "PXN V9 Gen 2"}

    def set_profile(self, profile): pass
    def set_enabled(self, flag): self.enabled = flag
    def toggle(self): self.enabled = not self.enabled
    def suspend(self): pass
    def resume(self): pass
    def set_toggle_key(self, key): pass
    def set_tick_rate(self, hz): pass
    def set_rumble(self, value): pass
    def rumble_test(self): pass
    def stop(self): pass


def снять(app, widget, name):
    for _ in range(5):
        app.processEvents()
    shot = OUT / name
    widget.grab().save(str(shot))
    print(f"  {name} ({shot.stat().st_size // 1024} КБ)")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="wheelscript-shots-")
    os.environ["APPDATA"] = tmp

    from wheelscript.app import create_app
    from wheelscript.model import default_config, gamepad_profile
    from wheelscript.qt.binding_dialog import BindingDialog
    from wheelscript.qt.main_window import MainWindow

    cfg = default_config()
    # Второй профиль - чтобы в кадре было видно, что их несколько и они переключаются.
    cfg = type(cfg)(cfg.settings, cfg.profiles + (gamepad_profile(),))

    app = create_app()
    service = Руль()
    win = MainWindow(service, cfg, Path(tmp) / "config.json")
    win.resize(1180, 700)
    win.show()
    app.processEvents()
    win.select(0)

    for mode, name in (("light", "window-light.png"), ("dark", "window-dark.png")):
        win.set_theme(mode)
        снять(app, win, name)

    # Окно настройки привязки: то самое, где «кликаешь в поле и жмёшь кнопку на руле».
    win.set_theme("dark")
    app.processEvents()
    dialog = BindingDialog(win, service, cfg.active.bindings[0], "Настройка привязки")
    dialog.show()
    снять(app, dialog, "binding-dark.png")
    dialog.reject()

    win.close()
    print(f"Готово: {OUT}")


if __name__ == "__main__":
    main()
