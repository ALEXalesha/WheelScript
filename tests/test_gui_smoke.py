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
