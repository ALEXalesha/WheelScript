"""Слой ввода на SDL без pygame (с подделкой SDL): значения как у pygame, события, открытие и закрытие."""

import os

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tests.fake_sdl import SDL_HAT_DOWN, SDL_HAT_LEFT, SDL_HAT_RIGHT, SDL_HAT_UP, Device, FakeSDL
from wheelscript import sdlinput
from wheelscript.sdlinput import SdlError, SdlInput


def opened(*devices):
    sdl = FakeSDL(*devices)
    inp = SdlInput(sdl)
    inp.init()
    return sdl, inp


@given(st.integers(-32768, 32767))
def test_axis_is_raw_over_32768_like_pygame(raw):
    """pygame 2.6 отдавал SDL_JoystickGetAxis / 32768.0: -32768 -> -1.0, 32767 -> чуть меньше 1."""
    sdl, inp = opened(Device(axes=[raw]))
    j = inp.scan()[0]
    v = j.get_axis(0)
    assert isinstance(v, float)
    assert v == raw / 32768.0
    assert -1.0 <= v < 1.0
    assert (v == 0.0) == (raw == 0)


HATS = {
    0: (0, 0),
    SDL_HAT_UP: (0, 1), SDL_HAT_DOWN: (0, -1), SDL_HAT_RIGHT: (1, 0), SDL_HAT_LEFT: (-1, 0),
    SDL_HAT_UP | SDL_HAT_RIGHT: (1, 1), SDL_HAT_UP | SDL_HAT_LEFT: (-1, 1),
    SDL_HAT_DOWN | SDL_HAT_RIGHT: (1, -1), SDL_HAT_DOWN | SDL_HAT_LEFT: (-1, -1),
}


@pytest.mark.parametrize("raw,xy", HATS.items())
def test_hat_is_xy_with_up_positive_like_pygame(raw, xy):
    sdl, inp = opened(Device(hats=[raw]))
    assert inp.scan()[0].get_hat(0) == xy


def test_counts_buttons_name_guid_instance():
    dev = Device(name="PXN V9 Руль", guid="0300aa", axes=[0] * 7, buttons=[0, 1, 0], hats=[0, 0])
    sdl, inp = opened(dev)
    j = inp.scan()[0]
    assert (j.get_numaxes(), j.get_numbuttons(), j.get_numhats()) == (7, 3, 2)
    assert [j.get_button(b) for b in range(3)] == [0, 1, 0]
    assert j.get_name() == "PXN V9 Руль"
    assert j.get_guid() == "0300aa"
    assert j.get_instance_id() == dev.iid


def test_init_queues_added_events_and_poll_reports_them():
    """SDL сообщает о подключённых устройствах при старте: список перестраивается ещё раз."""
    sdl, inp = opened(Device())
    assert inp.poll() == (True, [])
    assert inp.poll() == (False, [])


def test_poll_reports_axis_motion_and_device_changes():
    wheel = Device()
    sdl, inp = opened(wheel)
    inp.poll()
    sdl.move(wheel, 0, 0)
    sdl.move(wheel, 2, -100)
    assert inp.poll() == (False, [(wheel.iid, 0), (wheel.iid, 2)])
    pedals = sdl.plug(Device(name="pedals"))
    assert inp.poll() == (True, [])
    sdl.unplug(pedals)
    assert inp.poll() == (True, [])


def test_scan_reuses_open_devices_and_keep_closes_the_rest():
    wheel, pedals = Device(name="wheel"), Device(name="pedals")
    sdl, inp = opened(wheel, pedals)
    first = inp.scan()
    again = inp.scan()
    assert [a is b for a, b in zip(first, again)] == [True, True], "открытое устройство не переоткрывается"
    assert sdl.opens == ["wheel", "pedals"]
    inp.keep(again)
    assert sorted(sdl.live()) == ["pedals", "wheel"]

    sdl.unplug(pedals)
    now = inp.scan()
    assert [j.get_name() for j in now] == ["wheel"]
    assert sorted(sdl.live()) == ["pedals", "wheel"], "до keep() отключённое ещё открыто"
    inp.keep(now)
    assert sdl.live() == ["wheel"]
    assert all(h.refs == 1 for h in sdl.handles.values())

    sdl.plug(Device(name="pedals"))
    assert [j.get_name() for j in inp.scan()] == ["wheel", "pedals"]
    assert sdl.opens == ["wheel", "pedals", "pedals"], "переподключённое открывается заново"
    assert not sdl.violations


def test_keep_closes_device_left_out_on_purpose():
    """Свой виртуальный геймпад открывают, чтобы узнать слот, и тут же отпускают."""
    wheel, own = Device(name="wheel"), Device(name="own pad")
    sdl, inp = opened(wheel, own)
    joys = inp.scan()
    inp.keep([j for j in joys if j.get_name() != "own pad"])
    assert sdl.live() == ["wheel"]


def test_open_failure_raises_with_sdl_message():
    sdl, inp = opened(Device(name="ok"), Device(name="broken", fail_open=True))
    with pytest.raises(SdlError, match="Couldn't open joystick"):
        inp.open(1)
    assert inp.open(0).get_name() == "ok"


def test_scan_skips_device_that_fails_to_open():
    sdl, inp = opened(Device(name="broken", fail_open=True), Device(name="wheel"))
    assert [j.get_name() for j in inp.scan()] == ["wheel"]


def test_init_failure_raises_with_sdl_message():
    inp = SdlInput(FakeSDL(init_error="No joystick support"))
    with pytest.raises(SdlError, match="No joystick support"):
        inp.init()


def test_quit_closes_everything_then_quits_sdl():
    sdl, inp = opened(Device(name="a"), Device(name="b"))
    inp.keep(inp.scan())
    inp.quit()
    assert sdl.live() == [] and sdl.quit_called and not sdl.violations
    inp.quit()  # повторно - ничего не ломает
    assert not sdl.violations


def test_load_real_sdl_is_the_pinned_version_with_background_events(monkeypatch):
    """Настоящая SDL из pysdl2-dll: та же 2.28.4, что была у pygame 2.6.1.

    От версии зависят GUID устройств (ими подписаны привязки в config.json) и
    причуды haptic. Меняя pysdl2-dll, проверь руль вживую и поправь PINNED.
    """
    monkeypatch.delenv("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", raising=False)
    sdl = sdlinput.load()
    assert os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] == "1", "иначе в фоне руль молчит"
    assert sdlinput.version(sdl) == sdlinput.PINNED
    path = sdlinput.library_path(sdl)
    assert os.path.basename(path).lower() == "sdl2.dll"
    assert "sdl2dll" in path.replace("\\", "/").split("/"), "SDL2.dll из pysdl2-dll, а не случайная из PATH"
