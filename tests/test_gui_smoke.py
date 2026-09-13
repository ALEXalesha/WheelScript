"""Дымовой тест интерфейса с поддельным сервисом (без руля и без SendInput)."""

import queue

import pytest

from wheelscript.engine import DeviceState
from wheelscript.model import Action, Binding, InputSource, default_config
from wheelscript.service import DeviceInfo

tk = pytest.importorskip("tkinter")

KEY = "wheel"


class FakeService:
    def __init__(self):
        self.events = queue.SimpleQueue()
        self.enabled = False
        self.suspended = 0
        self.profiles = []
        self.state = DeviceState((0.0, None, -1.0), (False,) * 8, ((0, 0),))

    def snapshot(self):
        return {KEY: self.state}, [DeviceInfo(KEY, "V9GEN2", 3, 8, 1)]

    def device_names(self):
        return {KEY: "V9GEN2"}

    def set_profile(self, p): self.profiles.append(p)
    def set_enabled(self, f): self.enabled = f
    def toggle(self): self.enabled = not self.enabled
    def suspend(self): self.suspended += 1
    def resume(self): self.suspended -= 1
    def set_toggle_key(self, k): pass
    def set_tick_rate(self, hz): pass
    def set_rumble(self, v): self.rumble = v
    def rumble_test(self): self.rumble_tests = getattr(self, "rumble_tests", 0) + 1
    def stop(self): pass


@pytest.fixture(scope="module")
def tk_root():
    # Один Tk на процесс: повторный tk.Tk() после destroy() в Windows падает с TclError.
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"нет дисплея: {e}")
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def app(tk_root, tmp_path):
    from wheelscript.gui import App
    top = tk.Toplevel(tk_root)
    a = App(top, FakeService(), default_config(), tmp_path / "config.json")
    yield a
    a._closing = True
    top.destroy()


def test_app_builds_and_lists_default_bindings(app):
    app.root.update()
    assert len(app.tree.get_children()) == len(app.profile.bindings)
    assert app.service.profiles[-1] == app.profile


def test_toggle_enabled_column_and_persist(app):
    app._set_bindings([Binding.from_dict(b.to_dict() | {"enabled": False}) for b in app.profile.bindings])
    assert all(not b.enabled for b in app.profile.bindings)
    assert app.cfg_path.exists()


def test_fast_double_click_on_enabled_column_toggles_twice(app):
    """Регрессия: второй быстрый клик по «Вкл» приходит как <Double-1> и терялся."""
    class Ev:
        pass
    app.root.deiconify()
    app.root.update()
    x, y, w, h = app.tree.bbox("0", "#1")
    ev = Ev()
    ev.x, ev.y = x + w // 2, y + h // 2
    app._tree_click(ev)
    assert app.profile.bindings[0].enabled is False
    app.root.update()
    x, y, w, h = app.tree.bbox("0", "#1")
    ev.x, ev.y = x + w // 2, y + h // 2
    app._tree_double(ev)
    assert app.profile.bindings[0].enabled is True


def test_dialog_capture_and_save(app):
    svc = app.service
    result = {}

    def drive():
        dlg = [w for w in app.root.winfo_children() if isinstance(w, tk.Toplevel)][0]
        assert svc.suspended == 1, "маппинг на паузе, пока открыт редактор"
        dlg.input.start()
        svc.state = DeviceState((0.0, None, -1.0), (False, False, False, True) + (False,) * 4, ((0, 0),))
        dlg.after(60, lambda: finish(dlg))

    def finish(dlg):
        result["src"] = dlg.input.source
        dlg._ok()

    app.root.after(100, drive)
    app._add(Binding.make("test", InputSource(), Action.key(["e"])))
    assert result["src"] == InputSource.button(3, KEY)
    assert app.profile.bindings[-1].source == InputSource.button(3, KEY)
    assert svc.suspended == 0, "после закрытия редактора пауза снята"


def test_live_highlight(app):
    app.service.state = DeviceState((0.0, None, 1.0), (True,) + (False,) * 7, ((0, 1),))
    states, infos = app.service.snapshot()
    app._update_live(states, infos)
    live = [iid for iid in app.tree.get_children() if "live" in app.tree.item(iid, "tags")]
    names = {app.profile.bindings[int(i)].name for i in live}
    assert "Газ → W" in names and "A → ЛКМ" in names and "Камера вверх (крестовина ↑)" in names


def test_monitor_draws(app):
    states, infos = app.service.snapshot()
    app.monitor.update_view(states, infos)
    app.root.update()
    assert app.monitor.canvas.find_all()


def test_rumble_slider_saves_and_pushes(app):
    app.rumble_scale.set(40)
    app._set_rumble()
    assert app.cfg.settings.rumble == 40
    assert app.service.rumble == 0.4
    assert app.rumble_pct.cget("text") == "40%"
    app.rumble_test_btn.invoke()
    assert app.service.rumble_tests == 1
    app.service.events.put(("rumble_status", "вибрирует: V9GEN2"))
    app._poll()
    assert str(app.rumble_lbl.cget("text")) == "вибрирует: V9GEN2"


def _all_widgets(w):
    yield w
    for c in w.winfo_children():
        yield from _all_widgets(c)


def test_theme_switch_retints_everything(app):
    """После смены темы ни одно поле, холст или меню не остаётся в цветах старой темы."""
    from tkinter import ttk

    from wheelscript import theme
    for mode, pal in (("dark", theme.DARK), ("light", theme.LIGHT), ("dark", theme.DARK)):
        app._set_theme(mode)
        assert app.cfg.settings.theme == mode
        assert (ttk.Style(app.root).theme_use() == "clam") == pal["dark"]
        seen = set()
        for w in _all_widgets(app.root):
            cls = w.winfo_class()
            seen.add(cls)
            if cls == "Entry":
                assert str(w.cget("readonlybackground")) == pal["entry_bg"], w
            elif cls == "Canvas" and w is not app.dot:
                assert str(w.cget("background")) == pal["surface"], w
            elif cls == "Menu":
                assert str(w.cget("background")) == pal["menu_bg"], w
        assert {"Entry", "Canvas", "Menu"} <= seen
        assert str(app.tree.tag_configure("live", "background")) == pal["live_bg"]
        assert str(app.dot.cget("background")) == pal["bg"]
    for pal in (theme.LIGHT, theme.DARK):
        for k, v in pal.items():
            if isinstance(v, str):
                app.root.winfo_rgb(v)  # Tk понимает каждый цвет палитры
    app._set_theme("light")


def test_dialog_follows_dark_theme(app):
    from wheelscript import theme
    app._set_theme("dark")
    seen = {}

    def peek():
        dlg = [w for w in app.root.winfo_children() if isinstance(w, tk.Toplevel)][0]
        seen["bg"] = str(dlg.cget("background"))
        seen["preview"] = str(dlg.preview.cget("background"))
        seen["entry"] = str(dlg.input.entry.cget("readonlybackground"))
        dlg._cancel()

    app.root.after(100, peek)
    app._add(Binding.make("t", InputSource(), Action.key(["e"])))
    assert seen == {"bg": theme.DARK["bg"], "preview": theme.DARK["surface"], "entry": theme.DARK["entry_bg"]}
    app._set_theme("light")
