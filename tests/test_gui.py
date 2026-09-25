"""Интерфейс на Qt с поддельным сервисом (без руля, без SendInput, окна не видны)."""

import json
import queue
import random

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from wheelscript import storage, theme  # noqa: E402
from wheelscript.engine import DeviceState  # noqa: E402
from wheelscript.model import Action, Binding, Config, InputSource, default_config  # noqa: E402
from wheelscript.qt import dialogs  # noqa: E402
from wheelscript.qt.binding_dialog import BindingDialog  # noqa: E402
from wheelscript.qt.main_window import MainWindow  # noqa: E402
from wheelscript.service import DeviceInfo  # noqa: E402

KEY = "wheel"
IDLE = DeviceState((0.0, None, -1.0), (False,) * 8, ((0, 0),))


class FakeService:
    def __init__(self):
        self.events = queue.SimpleQueue()
        self.enabled = False
        self.suspended = 0
        self.max_suspended = 0
        self.profiles = []
        self.rumble = None
        self.rumble_tests = 0
        self.toggle_key = None
        self.tick = None
        self.connected = True
        self.state = IDLE

    def snapshot(self):
        if not self.connected:
            return {}, []
        return {KEY: self.state}, [DeviceInfo(KEY, "V9GEN2", 3, 8, 1)]

    def device_names(self):
        return {KEY: "V9GEN2"}

    def set_profile(self, p): self.profiles.append(p)
    def set_enabled(self, f): self.enabled = f
    def toggle(self): self.enabled = not self.enabled

    def suspend(self):
        self.suspended += 1
        self.max_suspended = max(self.max_suspended, self.suspended)

    def resume(self):
        self.suspended -= 1
        assert self.suspended >= 0, "resume без suspend"

    def set_toggle_key(self, k): self.toggle_key = k
    def set_tick_rate(self, hz): self.tick = hz
    def set_rumble(self, v): self.rumble = v
    def rumble_test(self): self.rumble_tests += 1
    def stop(self): pass


@pytest.fixture
def svc():
    return FakeService()


@pytest.fixture
def win(qapp, svc, tmp_path):
    w = MainWindow(svc, default_config(), tmp_path / "config.json")
    w.setAttribute(Qt.WA_DontShowOnScreen)
    w.show()
    QApplication.processEvents()
    yield w
    w.close()
    w.deleteLater()
    theme.apply(qapp, "light")


def _open(svc, tmp_path):
    w = MainWindow(svc, default_config(), tmp_path / "config.json")
    w.setAttribute(Qt.WA_DontShowOnScreen)
    w.show()
    QApplication.processEvents()
    return w


def _close(qapp, w):
    w.close()
    w.deleteLater()
    theme.apply(qapp, "light")


def test_window_comes_back_where_and_how_large_it_was(qapp, svc, tmp_path):
    w = _open(svc, tmp_path)
    # Экран самого окна, а не основной: скрытое окно (WA_DontShowOnScreen) не узнаёт,
    # что его передвинули на другой монитор. 960x600 влезает и в экран раннера 1024x768.
    area = w.screen().availableGeometry()
    x, y = area.x() + 40, area.y() + 60
    w.setGeometry(x, y, 960, 600)
    QApplication.processEvents()
    _close(qapp, w)
    assert isinstance(storage.load_window(tmp_path / "window.json"), str)
    again = _open(svc, tmp_path)
    try:
        assert (again.width(), again.height()) == (960, 600)
        assert (again.x(), again.y()) == (x, y)
        # config.json не трогали: место окна живёт отдельно.
        assert not (tmp_path / "config.json").exists() or "window" not in saved(again).to_dict()
    finally:
        _close(qapp, again)


@pytest.mark.parametrize("text", ["", "{", "[]", "null", '{"window": 42}', '{"window": "@@@"}',
                                  '{"window": "aGVsbG8="}', '{"window": "AAAA"}'])
def test_broken_window_file_gives_default_size(qapp, svc, tmp_path, text):
    fresh = _open(svc, tmp_path)  # файла ещё нет - размер по умолчанию
    want = fresh.size()
    fresh.close()  # закрытие само пишет window.json - его сейчас перезапишем мусором
    fresh.deleteLater()
    (tmp_path / "window.json").write_text(text, encoding="utf-8")
    w = _open(svc, tmp_path)
    try:
        assert w.size() == want
    finally:
        _close(qapp, w)


def rows(w):
    m = w.model
    return [[m.cell_text(r, c) for c in range(m.columnCount())] for r in range(m.rowCount())]


def saved(w) -> Config:
    return Config.from_dict(json.loads(w.cfg_path.read_text(encoding="utf-8")))


def assert_in_sync(w):
    """Инварианты: таблица = профиль, диск = cfg, сервис знает активный профиль, выделение в строках."""
    m = w.model
    assert m.bindings == w.profile.bindings
    assert m.rowCount() == len(w.profile.bindings)
    for r, b in enumerate(w.profile.bindings):
        assert m.cell_text(r, 0) == ("✔" if b.enabled else "—")
        assert m.cell_text(r, 1) == b.name
    if w.cfg_path.exists():
        assert saved(w).to_dict() == w.cfg.to_dict()
    assert w.service.profiles and w.service.profiles[-1] == w.profile
    sel = w.selected_row()
    assert sel is None or 0 <= sel < m.rowCount()
    assert [p.name for p in w.cfg.profiles] == [w.profile_cb.itemText(i) for i in range(w.profile_cb.count())]
    assert w.profile_cb.currentText() == w.profile.name
    assert w.row_buttons["edit"].isEnabled() == (sel is not None)


def cell_center(w, row, col):
    return w.table.visualRect(w.model.index(row, col)).center()


def click(w, row, col, double=False):
    vp = w.table.viewport()
    p = cell_center(w, row, col)
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, p)
    if double:
        QTest.mouseDClick(vp, Qt.LeftButton, Qt.NoModifier, p)


# ---- главное окно ------------------------------------------------------------------

def test_builds_and_lists_default_bindings(win, svc):
    assert win.model.rowCount() == len(win.profile.bindings) > 0
    assert svc.profiles[-1] == win.profile
    # Руль виден окну после первого опроса (таймер 40 мс). Раньше тест полагался на то,
    # что первый показ окна медленный и таймер успевает сработать; после других тестов
    # окна показ быстрее - опрашиваем явно.
    win.poll()
    assert "Маппинг выключен" in win.status.text()
    assert_in_sync(win)


def test_click_enabled_column_toggles_and_persists(win):
    was = win.profile.bindings[0].enabled
    click(win, 0, 0)
    assert win.profile.bindings[0].enabled is (not was)
    assert saved(win).active.bindings[0].enabled is (not was)
    assert_in_sync(win)


def test_fast_double_click_on_enabled_column_toggles_twice(win):
    was = win.profile.bindings[0].enabled
    click(win, 0, 0, double=True)
    assert win.profile.bindings[0].enabled is was


def test_click_selected_row_deselects_and_empty_area_too(win):
    click(win, 1, 1)
    assert win.selected_row() == 1
    QTest.qWait(QApplication.doubleClickInterval() + 30)
    click(win, 1, 1)
    assert win.selected_row() is None
    click(win, 2, 2)
    assert win.selected_row() == 2
    vp = win.table.viewport()
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, QPoint(20, vp.height() - 3))
    assert win.selected_row() is None
    assert_in_sync(win)


def test_double_click_on_selected_row_still_edits(win, monkeypatch):
    seen = []
    monkeypatch.setattr(win, "open_dialog", lambda b, t: seen.append((b, t)))
    win.select(0)
    click(win, 0, 2, double=True)
    assert seen and seen[0][0] == win.profile.bindings[0] and seen[0][1] == "Изменить привязку"


def test_enter_edits_delete_asks_escape_deselects(win, monkeypatch):
    seen = []
    monkeypatch.setattr(win, "open_dialog", lambda b, t: seen.append(b))
    win.select(1)
    QTest.keyClick(win.table, Qt.Key_Return)
    assert seen == [win.profile.bindings[1]]
    n = win.model.rowCount()
    monkeypatch.setattr(dialogs, "yes_no", lambda *a: False)
    QTest.keyClick(win.table, Qt.Key_Delete)
    assert win.model.rowCount() == n
    monkeypatch.setattr(dialogs, "yes_no", lambda *a: True)
    name = win.profile.bindings[1].name
    QTest.keyClick(win.table, Qt.Key_Delete)
    assert win.model.rowCount() == n - 1 and name not in [b.name for b in win.profile.bindings]
    assert win.selected_row() == 1
    QTest.keyClick(win.table, Qt.Key_Escape)
    assert win.selected_row() is None
    assert_in_sync(win)


def test_duplicate_and_move(win):
    win.select(0)
    first = win.profile.bindings[0]
    win._duplicate()
    assert win.profile.bindings[1].name == f"{first.name} (копия)" and win.selected_row() == 1
    win._move(-1)
    assert win.profile.bindings[0].name == f"{first.name} (копия)" and win.selected_row() == 0
    win._move(-1)  # выше некуда
    assert win.selected_row() == 0
    assert not win.row_buttons["up"].isEnabled() and win.row_buttons["down"].isEnabled()
    assert_in_sync(win)


def test_live_highlight(win, svc):
    svc.state = DeviceState((0.0, None, 1.0), (True,) + (False,) * 7, ((0, 1),))
    win.poll()
    live = {win.profile.bindings[r].name for r in range(win.model.rowCount()) if win.model.is_live(r)}
    assert "Газ → W" in live and "A → ЛКМ" in live and "Камера вверх (крестовина ↑)" in live
    assert win.model.data(win.model.index(0, 1), Qt.BackgroundRole) is not None or not win.model.is_live(0)
    svc.state = IDLE
    win.poll()
    assert not any(win.model.is_live(r) for r in range(win.model.rowCount()))


def test_disabled_bindings_are_not_live_and_grey(win, svc):
    bindings = [Binding.from_dict(b.to_dict() | {"enabled": False}) for b in win.profile.bindings]
    win._set_bindings(bindings)
    svc.state = DeviceState((0.0, None, 1.0), (True,) * 8, ((0, 1),))
    win.poll()
    assert not any(win.model.is_live(r) for r in range(win.model.rowCount()))
    assert win.model.data(win.model.index(0, 1), Qt.ForegroundRole) is not None


def test_monitor_follows_state(win, svc):
    win.poll()
    assert win.monitor.canvas.state == IDLE
    svc.state = DeviceState((0.5, 0.1, -1.0), (True,) * 8, ((1, 0),))
    win.poll()
    assert win.monitor.canvas.state == svc.state
    assert not win.monitor.update_view(*svc.snapshot()), "без изменений — без перерисовки"
    img = win.monitor.canvas.grab()
    assert not img.isNull()
    svc.connected = False
    win.poll()
    assert win.monitor.canvas.state is None and "Руль не найден" in win.status.text()


def test_run_button_and_status(win, svc):
    win.poll()
    QTest.mouseClick(win.run_btn, Qt.LeftButton)
    assert svc.enabled and "ВКЛЮЧЁН" in win.status.text() and win.run_btn.text().startswith("Выключить")
    QTest.mouseClick(win.run_btn, Qt.LeftButton)
    assert not svc.enabled and win.run_btn.text().startswith("Включить")


def test_rumble_slider_pushes_and_saves(win, svc):
    win.rumble_slider.setValue(40)
    assert svc.rumble == 0.4 and win.rumble_pct.text() == "40%"
    win._set_rumble()
    assert win.cfg.settings.rumble == 40 and saved(win).settings.rumble == 40
    QTest.mouseClick(win.rumble_test_btn, Qt.LeftButton)
    assert svc.rumble_tests == 1
    svc.events.put(("rumble_status", "вибрирует: V9GEN2"))
    svc.events.put(("pad_status", "подключён"))
    svc.events.put(("error", "что-то сломалось"))
    win.poll()
    assert win.rumble_lbl.text() == "вибрирует: V9GEN2"
    assert win.pad_lbl.text() == "Геймпад: подключён"
    assert "что-то сломалось" in win.error_lbl.text()


def test_tick_rate_clamped_and_saved(win, svc):
    win.tick_spin.setValue(250)
    win._set_tick()
    assert svc.tick == 250 and saved(win).settings.tick_rate == 250
    win.tick_spin.setValue(99999)  # QSpinBox сам ограничит сверху
    win._set_tick()
    assert saved(win).settings.tick_rate == win.tick_spin.maximum()


def test_start_enabled_checkbox_saves(win):
    win.start_cb.setChecked(True)
    assert saved(win).settings.start_enabled is True
    win.start_cb.setChecked(False)
    assert saved(win).settings.start_enabled is False


def test_theme_switch_changes_palette_and_saves(win, qapp):
    for mode, dark in (("dark", True), ("light", False), ("dark", True)):
        win.set_theme(mode)
        assert win.cfg.settings.theme == mode and saved(win).settings.theme == mode
        assert theme.P["dark"] is dark and theme.is_dark(qapp.palette()) is dark
        assert theme.P["error"] in win.error_lbl.styleSheet()


# ---- горячая клавиша -----------------------------------------------------------------

def native_key(widget, qt_key, vk, scan, press=True, mods=Qt.NoModifier, native_mods=0):
    ev = QKeyEvent(QEvent.KeyPress if press else QEvent.KeyRelease, qt_key, mods, scan, vk, native_mods, "")
    QApplication.sendEvent(widget, ev)


def test_hotkey_capture_suspends_and_saves(win, svc):
    f = win.hotkey
    QTest.mouseClick(f.line, Qt.LeftButton)
    assert f.capturing and svc.suspended == 1, "пока ловим клавишу, маппинг на паузе"
    native_key(f.line, Qt.Key_F9, 0x78, 0x43)
    native_key(f.line, Qt.Key_F9, 0x78, 0x43, press=False)
    assert not f.capturing and svc.suspended == 0
    assert svc.toggle_key == "f9" and saved(win).settings.toggle_key == "f9"
    assert "F9" in win.run_btn.text()


def test_hotkey_capture_escape_cancels(win, svc):
    before = win.cfg.settings.toggle_key
    QTest.mouseClick(win.hotkey.line, Qt.LeftButton)
    native_key(win.hotkey.line, Qt.Key_Escape, 0x1B, 0x01)
    assert not win.hotkey.capturing and svc.suspended == 0
    assert win.cfg.settings.toggle_key == before


def test_hotkey_capture_ends_on_focus_loss_and_timeout(win, svc):
    QTest.mouseClick(win.hotkey.line, Qt.LeftButton)
    win.hotkey.focus_lost()
    assert not win.hotkey.capturing and svc.suspended == 0
    QTest.mouseClick(win.hotkey.line, Qt.LeftButton)
    win.hotkey.timer.timeout.emit()
    assert not win.hotkey.capturing and svc.suspended == 0


def test_hotkey_clear_button(win, svc):
    win.hotkey._set(("f9",))
    QTest.mouseClick(win.hotkey.clear_button, Qt.LeftButton)
    assert svc.toggle_key == "" and saved(win).settings.toggle_key == ""


def test_combo_capture_orders_modifiers(qapp):
    from wheelscript.qt.fields import KeyField
    f = KeyField(("w",), combo=True)
    got = []
    f.value_changed.connect(got.append)
    f.start()
    native_key(f.line, Qt.Key_S, 0x53, 0x1F)
    native_key(f.line, Qt.Key_Control, 0x11, 0x1D, native_mods=0x01000000)  # правый Ctrl
    native_key(f.line, Qt.Key_S, 0x53, 0x1F, press=False)
    native_key(f.line, Qt.Key_Control, 0x11, 0x1D, press=False, native_mods=0x01000000)
    assert got == [("rctrl", "s")]
    f.deleteLater()


def test_tab_is_captured_not_focus_change(qapp):
    from wheelscript.qt.fields import KeyField
    f = KeyField(("w",), combo=False)
    f.start()
    native_key(f.line, Qt.Key_Tab, 0x09, 0x0F)
    native_key(f.line, Qt.Key_Tab, 0x09, 0x0F, press=False)
    assert f.value == ("tab",)
    f.deleteLater()


# ---- профили -------------------------------------------------------------------------

def test_profile_new_rename_copy_delete(win, svc, monkeypatch):
    answers = iter(["Гонки", "Гонки 2", "  ", "Гонки 2"])
    monkeypatch.setattr(dialogs, "ask_text", lambda *a: next(answers))
    errors = []
    monkeypatch.setattr(dialogs, "error", lambda _p, t: errors.append(t))
    win._profile_new()
    assert win.profile.name == "Гонки" and win.profile.bindings == ()
    win._profile_copy()
    assert win.profile.name == "Гонки 2"
    win._profile_rename()  # пустое имя
    assert errors and "пустым" in errors[-1]
    win._profile_new()  # такое имя уже есть
    assert "уже есть" in errors[-1]
    monkeypatch.setattr(dialogs, "yes_no", lambda *a: True)
    n = len(win.cfg.profiles)
    win._profile_delete()
    assert len(win.cfg.profiles) == n - 1 and "Гонки 2" not in [p.name for p in win.cfg.profiles]
    assert_in_sync(win)


def test_last_profile_cannot_be_deleted(win, monkeypatch):
    infos = []
    monkeypatch.setattr(dialogs, "info", lambda _p, t: infos.append(t))
    monkeypatch.setattr(dialogs, "yes_no", lambda *a: True)
    while len(win.cfg.profiles) > 1:
        win._profile_delete()
    win._profile_delete()
    assert len(win.cfg.profiles) == 1 and "единственный" in infos[-1]


def test_profile_combo_switches_active(win, monkeypatch):
    monkeypatch.setattr(dialogs, "ask_text", lambda *a: "Второй")
    first = win.profile.name
    win._profile_new()
    win._select_profile(0)
    assert win.profile.name == first and win.service.profiles[-1].name == first
    assert_in_sync(win)


def test_export_import_round_trip(win, tmp_path, monkeypatch):
    path = tmp_path / "p.json"
    monkeypatch.setattr(dialogs, "save_path", lambda *a: str(path))
    win._profile_export()
    assert path.exists()
    monkeypatch.setattr(dialogs, "open_path", lambda *a: str(path))
    before = win.profile
    win._profile_import()
    assert win.profile.bindings == before.bindings and win.profile.name != before.name
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    monkeypatch.setattr(dialogs, "open_path", lambda *a: str(bad))
    errors = []
    monkeypatch.setattr(dialogs, "error", lambda _p, t: errors.append(t))
    win._profile_import()
    assert errors and "импортировать" in errors[-1]


def test_profile_menus_have_all_actions(win):
    names = [a.text() for a in win.profile_menu.actions() if not a.isSeparator()]
    assert len(names) == 8 and names[0].startswith("Новый пустой")
    from wheelscript.presets import PRESETS
    presets = [a.text() for a in win.add_menu.actions() if not a.isSeparator()]
    assert presets == [p[0] for p in PRESETS if p is not None]


# ---- диалог привязки -------------------------------------------------------------------

@pytest.fixture
def dlg_for(win, svc):
    made = []

    def make(binding=None, title="t"):
        d = BindingDialog(win, svc, binding or Binding.make("test", InputSource(), Action.key(["e"])), title)
        made.append(d)
        return d
    yield make
    for d in made:
        if d.isVisible() or not d._resumed:
            d.reject()
        d.deleteLater()


def test_dialog_suspends_until_closed_every_way(win, svc, dlg_for, monkeypatch):
    monkeypatch.setattr(dialogs, "yes_no", lambda *a: True)
    for close in ("accept", "reject", "escape", "done_twice"):
        d = dlg_for()
        assert svc.suspended == 1, close
        if close == "accept":
            d.accept_binding()
        elif close == "reject":
            d.reject()
        elif close == "escape":
            QTest.keyClick(d, Qt.Key_Escape)
        else:
            d.reject()
            d.reject()
        assert svc.suspended == 0, close
    assert svc.max_suspended == 1


def test_dialog_capture_from_wheel_and_save(win, svc, dlg_for):
    d = dlg_for()
    d.input.start()
    assert d.input.capturing
    svc.state = DeviceState((0.0, None, -1.0), (False, False, False, True) + (False,) * 4, ((0, 0),))
    d.input._poll()
    assert not d.input.capturing and d.input.source == InputSource.button(3, KEY)
    d.accept_binding()
    assert d.result_binding.source == InputSource.button(3, KEY)
    assert d.result_binding.action.keys == ("e",)


def test_dialog_capture_escape_does_not_close(win, svc, dlg_for):
    d = dlg_for()
    d.input.start()
    QTest.keyClick(d.input.line, Qt.Key_Escape)
    assert not d.input.capturing and svc.suspended == 1


def test_dialog_capture_without_wheel_warns(win, svc, dlg_for, monkeypatch):
    warnings = []
    monkeypatch.setattr(dialogs, "warning", lambda _p, t: warnings.append(t))
    svc.connected = False
    d = dlg_for()
    d.input.start()
    assert not d.input.capturing and "не подключён" in warnings[0]


def test_dialog_capture_times_out(win, svc, dlg_for):
    d = dlg_for()
    d.input.start()
    d.input._deadline = 0
    d.input._poll()
    assert not d.input.capturing


def test_dialog_axis_source_and_tune_rows(win, svc, dlg_for):
    d = dlg_for(Binding.make("ось", InputSource.axis(0, "pos", KEY), Action.key(["w"])))
    assert d.axis_mode.isVisibleTo(d) and not d.hat_mode.isVisibleTo(d)
    assert d.visible_tunes() == ["threshold"]
    d.kind.set_key("mouse_move")
    d._on_kind("mouse_move")
    assert d.input.source.mode == "full", "для движения мыши ось нужна целиком"
    assert d.visible_tunes() == ["deadzone", "curve"]
    b = d.build()
    assert b.action.kind == "mouse_move" and b.source.mode == "full"


def test_dialog_every_kind_builds(win, svc, dlg_for):
    from wheelscript.qt.binding_dialog import KINDS
    d = dlg_for()
    for k in KINDS:
        d.kind.set_key(k)
        d._on_kind(k)
        b = d.build()
        assert b.action.kind == k
        assert Binding.from_dict(b.to_dict()) == b


def test_dialog_key_without_keys_refused(win, svc, dlg_for, monkeypatch):
    errors = []
    monkeypatch.setattr(dialogs, "error", lambda _p, t: errors.append(t))
    d = dlg_for()
    d.keys_val = ()
    d.accept_binding()
    assert d.result_binding is None and errors == ["Выбери клавишу."]


def test_dialog_unset_source_asks(win, svc, dlg_for, monkeypatch):
    monkeypatch.setattr(dialogs, "yes_no", lambda *a: False)
    d = dlg_for()
    d.accept_binding()
    assert d.result_binding is None and svc.suspended == 1


def test_dialog_preview_texts(win, svc, dlg_for):
    d = dlg_for(Binding.make("b", InputSource.button(0, KEY), Action.key(["w"])))
    svc.state = DeviceState((0.0, None, -1.0), (True,) + (False,) * 7, ((0, 0),))
    d._tick()
    assert "СРАБОТАЛО" in d.preview_text.text()
    svc.state = IDLE
    d._tick()
    assert "не нажато" in d.preview_text.text()
    d2 = dlg_for(Binding.make("a", InputSource(), Action.key(["w"])))
    d2._tick()
    assert "нет данных" in d2.preview_text.text()


def test_cancelled_add_changes_nothing(win, svc):
    before = win.cfg.to_dict()

    def cancel():
        m = QApplication.activeModalWidget()
        assert isinstance(m, BindingDialog)
        m.reject()
    QTimer.singleShot(50, cancel)
    win._add(Binding.make("x", InputSource(), Action.key(["e"])))
    assert win.cfg.to_dict() == before and svc.suspended == 0


def test_real_modal_add_saves(win, svc, monkeypatch):
    monkeypatch.setattr(dialogs, "yes_no", lambda *a: True)
    n = len(win.profile.bindings)

    def ok():
        m = QApplication.activeModalWidget()
        m.name.setText("Новая")
        m.accept_binding()
    QTimer.singleShot(50, ok)
    win._add(Binding.make("x", InputSource(), Action.key(["e"])))
    assert len(win.profile.bindings) == n + 1 and win.profile.bindings[-1].name == "Новая"
    assert win.selected_row() == n and svc.suspended == 0
    assert_in_sync(win)


# ---- случайные последовательности ------------------------------------------------------

def test_random_sequences(win, svc, monkeypatch):
    monkeypatch.setattr(dialogs, "yes_no", lambda *a: True)
    monkeypatch.setattr(dialogs, "info", lambda *a: None)
    monkeypatch.setattr(dialogs, "error", lambda *a: None)
    names = iter(f"П{i}" for i in range(10_000))
    monkeypatch.setattr(dialogs, "ask_text", lambda *a: next(names))
    monkeypatch.setattr(win, "open_dialog", lambda b, t: Binding.from_dict(b.to_dict() | {"name": b.name + "*"}))
    rng = random.Random(3)
    for step in range(300):
        op = rng.choice(["toggle", "select", "deselect", "dup", "del", "up", "down", "edit", "add",
                         "profile_new", "profile_select", "profile_del", "poll", "theme"])
        n = win.model.rowCount()
        if op == "toggle" and n:
            win._toggle_binding(rng.randrange(n))
        elif op == "select" and n:
            win.select(rng.randrange(n))
        elif op == "deselect":
            win.select(None)
        elif op == "dup":
            win._duplicate()
        elif op == "del":
            win._delete()
        elif op == "up":
            win._move(-1)
        elif op == "down":
            win._move(1)
        elif op == "edit":
            win._edit()
        elif op == "add":
            win._add(Binding.make("r", InputSource.button(rng.randrange(8), KEY), Action.key(["e"])))
        elif op == "profile_new" and len(win.cfg.profiles) < 10:
            win._profile_new()
        elif op == "profile_select":
            win._select_profile(rng.randrange(len(win.cfg.profiles)))
        elif op == "profile_del":
            win._profile_delete()
        elif op == "poll":
            svc.state = DeviceState((rng.uniform(-1, 1), None, -1.0),
                                    tuple(rng.random() < 0.3 for _ in range(8)), ((0, rng.choice([-1, 0, 1])),))
            win.poll()
        elif op == "theme":
            win.set_theme(rng.choice(["light", "dark", "system"]))
        assert_in_sync(win)
        assert svc.suspended == 0, (step, op)


def test_table_fits_without_horizontal_scroll(win):
    for width in (900, 1180, 1600):
        win.resize(width, 700)
        QApplication.processEvents()
        header = win.table.horizontalHeader()
        assert header.length() <= win.table.viewport().width() + 1, width
        assert win.table.horizontalScrollBar().maximum() == 0


def test_window_title_has_version(win):
    from wheelscript import __version__
    assert __version__ in win.windowTitle() and __version__.startswith("3.")


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_selected_row_clearly_marked(win, mode):
    win.set_theme(mode)
    win.select(None)
    QApplication.processEvents()
    rect = win.table.visualRect(win.model.index(6, 2))  # строка, которая не подсвечена как «срабатывает»
    p = rect.center() + QPoint(rect.width() // 3, 0)  # пустое место ячейки, не текст

    def pixel():
        img = win.table.viewport().grab().toImage()
        return img.pixelColor(p)
    plain = pixel()
    win.select(6)
    QApplication.processEvents()
    sel = pixel()
    diff = abs(plain.red() - sel.red()) + abs(plain.green() - sel.green()) + abs(plain.blue() - sel.blue())
    assert diff >= 40, (mode, plain.name(), sel.name())
    live = theme.P["live_bg"]
    from PySide6.QtGui import QColor
    lc = QColor(live)
    assert abs(lc.red() - sel.red()) + abs(lc.green() - sel.green()) + abs(lc.blue() - sel.blue()) >= 30, \
        "выделение не путается с подсветкой срабатывающих строк"


def test_table_columns_fill_the_width(win):
    for width in (900, 1400):
        win.resize(width, 700)
        QApplication.processEvents()
        header = win.table.horizontalHeader()
        assert abs(header.length() - win.table.viewport().width()) <= 2, width


def test_escape_in_dialog_cancels_capture_before_closing(win, svc, dlg_for):
    d = dlg_for()
    d.input.start()
    QTest.keyClick(d, Qt.Key_Escape)  # фокус не в поле: Esc приходит самому диалогу
    assert not d.input.capturing and d.result() == 0 and svc.suspended == 1, "окно не закрылось"
    QTest.keyClick(d, Qt.Key_Escape)  # второй Esc уже закрывает
    assert svc.suspended == 0


def test_captured_half_axis_becomes_whole_for_mouse_move(win, svc, dlg_for):
    d = dlg_for(Binding.make("m", InputSource(), Action.move("right")))
    svc.state = DeviceState((0.0, 0.0, -1.0), (False,) * 8, ((0, 0),))
    d.input.start()
    svc.state = DeviceState((0.8, 0.0, -1.0), (False,) * 8, ((0, 0),))
    d.input._poll()
    assert d.input.source.kind == "axis" and d.input.source.mode == "full"
    assert d.visible_tunes() == ["deadzone", "curve"]
