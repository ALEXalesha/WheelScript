"""WheelScript.exe --selftest: сервис без окна, список устройств в файл, ничего не нажимает и не трясёт."""

import pytest

from tests.fake_sdl import Device, FakeSDL
from wheelscript import app, sdlinput, selftest, sendinput


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(sendinput, "apply", lambda events: out.extend(events))
    monkeypatch.setattr(sendinput, "is_key_down", lambda name: pytest.fail(f"самопроверка читает клавишу {name}"))
    return out


def test_selftest_lists_devices_and_says_ok(tmp_path, monkeypatch, sent):
    sdl = FakeSDL(Device(name="V9GEN2", guid="w", axes=[0] * 7, buttons=[0] * 12, hats=[0]))
    monkeypatch.setattr(sdlinput, "load", lambda: sdl)
    out = tmp_path / "selftest.txt"
    assert selftest.run(out, seconds=0.3) == 0
    text = out.read_text(encoding="utf-8")
    assert "result: OK" in text
    assert "devices: 1" in text
    assert "V9GEN2 | guid w | axes 7 | buttons 12 | hats 1" in text
    assert "rumble: вибрирует: V9GEN2" in text
    assert sent == [], "самопроверка ничего не нажимает"
    assert not [r for r in sdl.rumble if r[0] == "play"], "и руль не трясёт"
    assert sdl.live() == [] and sdl.quit_called, "SDL закрыта"


def test_selftest_pauses_mapping_and_disables_hotkey_before_start(tmp_path, monkeypatch, sent):
    """Две защиты, и каждая нужна сама по себе: пауза не даёт движку ничего нажать,
    пустая горячая клавиша - включить маппинг, даже если пауза когда-нибудь снимется."""
    from wheelscript import service
    calls = []
    for name in ("suspend", "set_toggle_key", "start"):
        orig = getattr(service.InputService, name)

        def spy(self, *args, _orig=orig, _name=name):
            calls.append((_name, args))
            return _orig(self, *args)
        monkeypatch.setattr(service.InputService, name, spy)
    monkeypatch.setattr(sdlinput, "load", lambda: FakeSDL(Device()))
    assert selftest.run(tmp_path / "r.txt", seconds=0.1) == 0
    assert sorted(calls[:2]) == [("set_toggle_key", ("",)), ("suspend", ())]
    assert calls[2] == ("start", ())


def test_selftest_without_devices_is_still_ok(tmp_path, monkeypatch, sent):
    monkeypatch.setattr(sdlinput, "load", lambda: FakeSDL())
    out = tmp_path / "selftest.txt"
    assert selftest.run(out, seconds=0.2) == 0
    text = out.read_text(encoding="utf-8")
    assert "devices: 0" in text and "result: OK" in text


def test_selftest_reports_sdl_failure(tmp_path, monkeypatch, sent):
    monkeypatch.setattr(sdlinput, "load", lambda: FakeSDL(init_error="No joystick support"))
    out = tmp_path / "selftest.txt"
    assert selftest.run(out, seconds=0.2) == 1
    text = out.read_text(encoding="utf-8")
    assert "result: FAIL" in text and "No joystick support" in text


def test_main_runs_selftest_without_window(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(selftest, "run", lambda path, seconds=2.0: calls.append((path, seconds)) or 0)
    monkeypatch.setattr(app, "create_app", lambda: pytest.fail("самопроверка открыла окно"))
    with pytest.raises(SystemExit) as done:
        app.main(["--selftest", str(tmp_path / "r.txt")])
    assert done.value.code == 0
    assert calls == [(tmp_path / "r.txt", 2.0)]


def test_main_selftest_default_path_is_in_temp(monkeypatch):
    import tempfile
    from pathlib import Path
    calls = []
    monkeypatch.setattr(selftest, "run", lambda path, seconds=2.0: calls.append(path) or 1)
    with pytest.raises(SystemExit) as done:
        app.main(["--selftest"])
    assert done.value.code == 1
    assert calls == [Path(tempfile.gettempdir()) / "WheelScript-selftest.txt"]
