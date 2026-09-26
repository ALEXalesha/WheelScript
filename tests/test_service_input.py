"""Сервис ввода поверх SDL без pygame (с подделкой SDL): устройства, оси, горячее подключение, вибромотор."""

import queue
import time

import pytest

from tests.fake_sdl import SDL_HAT_UP, Device, FakeSDL
from wheelscript import sdlinput, sendinput
from wheelscript.sdlinput import SdlInput
from wheelscript.service import DeviceInfo, InputService


def attached(sdl):
    """Сервис без потока: SDL уже поднята, как после начала _run()."""
    svc = InputService()
    svc._input = SdlInput(sdl)
    svc._input.init()
    return svc


def next_event(svc, kind, pred=lambda v: True, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            ev = svc.events.get(timeout=0.02)
        except queue.Empty:
            continue
        if ev[0] == kind and pred(ev[1]):
            return ev[1]
    raise AssertionError(f"не дождались события {kind}")


def until(cond, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.01)
    raise AssertionError("условие так и не выполнилось")


@pytest.fixture
def running(monkeypatch):
    """Настоящий поток сервиса с подделкой SDL. Всё, что сервис отправил бы в SendInput, - в sent."""
    services, sent = [], []
    monkeypatch.setattr(sendinput, "apply", lambda events: sent.extend(events))

    def start(sdl):
        monkeypatch.setattr(sdlinput, "load", lambda: sdl)
        svc = InputService(tick_rate=500)
        svc.set_toggle_key("")  # F8 человека за клавиатурой не должен включить маппинг посреди теста
        svc.sent = sent
        svc.start()
        services.append(svc)
        return svc

    yield start
    for svc in services:
        svc.stop()


def test_devices_get_guid_keys_and_twins_get_numbered():
    a = Device(name="V9GEN2", guid="aa", axes=[0] * 7, buttons=[0] * 12, hats=[0])
    b = Device(name="V9GEN2", guid="aa", axes=[0] * 3, buttons=[0] * 2, hats=[])
    c = Device(name="Pedals", guid="cc", axes=[0] * 3, buttons=[], hats=[])
    svc = attached(FakeSDL(a, b, c))
    svc._rebuild()
    _, infos = svc.snapshot()
    assert infos == [DeviceInfo("aa", "V9GEN2", 7, 12, 1), DeviceInfo("aa#2", "V9GEN2", 3, 2, 0),
                     DeviceInfo("cc", "Pedals", 3, 0, 0)]
    assert svc.device_names() == {"aa": "V9GEN2", "aa#2": "V9GEN2", "cc": "Pedals"}


def test_axes_are_unknown_until_they_report():
    """Регрессия движка: до первого движения SDL отдаёт у педали 0, и педаль «нажата наполовину»."""
    wheel = Device(guid="w", axes=[0, 0, -32768], buttons=[0, 1], hats=[SDL_HAT_UP])
    sdl = FakeSDL(wheel)
    svc = attached(sdl)
    svc._rebuild()
    state = svc._read()["w"]
    assert state.axes == (None, None, -1.0)
    assert state.buttons == (False, True)
    assert state.hats == ((0, 1),)
    assert svc._pump() is True          # JOYDEVICEADDED при старте SDL
    sdl.move(wheel, 0, 0)               # руль в центре, но SDL прислал движение: ось живая
    assert svc._pump() is False
    assert svc._read()["w"].axes == (0.0, None, -1.0)


def test_rebuild_keeps_devices_open_once():
    wheel, pedals = Device(name="wheel", guid="w"), Device(name="pedals", guid="p")
    sdl = FakeSDL(wheel, pedals)
    svc = attached(sdl)
    for _ in range(4):
        svc._rebuild()
    assert sdl.opens == ["wheel", "pedals"]
    assert all(h.refs == 1 for h in sdl.handles.values())


def test_own_virtual_gamepad_is_hidden_and_released():
    wheel = Device(name="wheel", guid="w")
    own = Device(name="Controller (Xbox 360)", guid="x", player=1)
    sdl = FakeSDL(wheel, own)
    svc = attached(sdl)
    svc._own_slot = 1
    svc._rebuild()
    assert [d.name for d in svc.snapshot()[1]] == ["wheel"]
    assert sdl.live() == ["wheel"], "свой геймпад не держим открытым"
    svc._own_slot = None
    svc._rebuild()
    assert [d.name for d in svc.snapshot()[1]] == ["wheel", "Controller (Xbox 360)"]


def test_device_that_fails_to_open_is_skipped():
    sdl = FakeSDL(Device(name="broken", guid="b", fail_open=True), Device(name="wheel", guid="w"))
    svc = attached(sdl)
    svc._rebuild()
    assert [d.name for d in svc.snapshot()[1]] == ["wheel"]


def test_unplugged_wheel_loses_haptic_before_its_joystick():
    wheel = Device(name="V9GEN2", guid="w")
    sdl = FakeSDL(wheel)
    svc = attached(sdl)
    svc._rebuild()
    assert svc.rumble_status == "вибрирует: V9GEN2"
    sdl.unplug(wheel)
    svc._pump()
    svc._rebuild()
    assert sdl.live() == [] and not sdl.haptics
    assert svc.rumble_status == "руль не подключён"
    assert not sdl.violations, sdl.violations


def test_haptic_survives_startup_rebuild_and_rumbles_the_wheel(running):
    """Регрессия: при старте SDL шлёт JOYDEVICEADDED, сервис перестраивает список, и
    переоткрытие haptic молча выключало вибрацию (DirectInput у PXN V9)."""
    wheel = Device(name="V9GEN2", guid="w")
    sdl = FakeSDL(wheel)
    svc = running(sdl)
    next_event(svc, "devices")
    next_event(svc, "devices")          # вторая перестройка - от JOYDEVICEADDED
    assert sdl.haptic_opens == [wheel.iid]
    assert svc.rumble_status == "вибрирует: V9GEN2"
    svc.rumble_test()
    until(lambda: any(r[0] == "play" and r[1] == 1000 + wheel.iid for r in sdl.rumble))


def test_loop_publishes_state_and_follows_hotplug(running):
    wheel = Device(name="wheel", guid="w", axes=[0, 0, -32768], buttons=[0, 1], hats=[0])
    sdl = FakeSDL(wheel)
    svc = running(sdl)
    until(lambda: "w" in svc.snapshot()[0])
    until(lambda: svc.snapshot()[0]["w"].axes[2] == -1.0)
    assert svc.snapshot()[0]["w"].buttons == (False, True)

    pedals = sdl.plug(Device(name="pedals", guid="p", axes=[32767], buttons=[], hats=[]))
    next_event(svc, "devices", lambda infos: [d.name for d in infos] == ["wheel", "pedals"])
    until(lambda: "p" in svc.snapshot()[0])

    sdl.unplug(wheel)
    next_event(svc, "devices", lambda infos: [d.name for d in infos] == ["pedals"])
    until(lambda: sdl.live() == ["pedals"])
    assert list(svc.snapshot()[0]) == ["p"]
    assert not sdl.violations
    assert svc.sent == [], "выключенный маппинг ничего не нажимает"


def test_stop_closes_everything(running):
    sdl = FakeSDL(Device(name="wheel", guid="w"), Device(name="pedals", guid="p"))
    svc = running(sdl)
    next_event(svc, "devices")
    svc.stop()
    assert not svc._thread.is_alive()
    assert sdl.live() == [] and not sdl.haptics and sdl.quit_called
    assert not sdl.violations, sdl.violations


def test_sdl_init_error_is_reported_and_thread_ends(running):
    svc = running(FakeSDL(init_error="No joystick support"))
    text = next_event(svc, "error")
    assert "SDL" in text and "No joystick support" in text
    svc._thread.join(2)
    assert not svc._thread.is_alive()
