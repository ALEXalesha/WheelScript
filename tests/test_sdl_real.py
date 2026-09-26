"""Слой ввода с настоящей SDL из pysdl2-dll и виртуальным рулём SDL - без железа.

Подделка SDL проверяет логику, а здесь проверяется связка с библиотекой: сигнатуры
PySDL2, перевод осей и хатки, события подключения и отключения, закрытие. Виртуальный
руль SDL (SDL_JoystickAttachVirtual) живёт только внутри этого процесса: системе и
играм он не виден, ничего не нажимает.
"""

import pytest

from wheelscript import sdlinput
from wheelscript.sdlinput import SdlInput

pytest.importorskip("sdl2")


@pytest.fixture
def real():
    sdl = sdlinput.load()
    inp = SdlInput(sdl)
    inp.init()
    inp.poll()  # события о настоящих устройствах этой машины, если они есть
    yield sdl, inp
    inp.quit()


def virtual(sdl, inp, axes=3, buttons=4, hats=1):
    idx = sdl.SDL_JoystickAttachVirtual(sdl.SDL_JOYSTICK_TYPE_WHEEL, axes, buttons, hats)
    assert idx >= 0, sdl.SDL_GetError()
    iid = sdl.SDL_JoystickGetDeviceInstanceID(idx)
    return idx, iid


def find(joys, iid):
    return next(j for j in joys if j.get_instance_id() == iid)


def test_virtual_wheel_reads_like_pygame(real):
    sdl, inp = real
    idx, iid = virtual(sdl, inp)
    assert inp.poll()[0] is True, "JOYDEVICEADDED"
    j = find(inp.scan(), iid)
    assert (j.get_numaxes(), j.get_numbuttons(), j.get_numhats()) == (3, 4, 1)
    assert j.get_name() == "Virtual Wheel"
    assert len(j.get_guid()) == 32 and int(j.get_guid(), 16) >= 0

    sdl.SDL_JoystickSetVirtualAxis(j.ptr, 0, 16384)
    sdl.SDL_JoystickSetVirtualAxis(j.ptr, 1, -32768)
    sdl.SDL_JoystickSetVirtualAxis(j.ptr, 2, 32767)
    sdl.SDL_JoystickSetVirtualButton(j.ptr, 2, 1)
    sdl.SDL_JoystickSetVirtualHat(j.ptr, 0, sdl.SDL_HAT_LEFTUP)
    rebuild, moved = inp.poll()  # SDL применяет значения виртуального руля при опросе
    assert not rebuild
    assert {(iid, 0), (iid, 1), (iid, 2)} <= set(moved)
    assert [j.get_axis(a) for a in range(3)] == [0.5, -1.0, 32767 / 32768]
    assert [j.get_button(b) for b in range(4)] == [0, 0, 1, 0]
    assert j.get_hat(0) == (-1, 1)

    sdl.SDL_JoystickDetachVirtual(idx)
    assert inp.poll()[0] is True, "JOYDEVICEREMOVED"
    now = inp.scan()
    assert iid not in [x.get_instance_id() for x in now]
    inp.keep(now)
    assert not sdl.SDL_JoystickFromInstanceID(iid), "отключённый руль закрыт"


def test_virtual_wheel_has_no_haptic_and_rumble_stays_quiet(real):
    """У виртуального руля нет вибромотора: WheelHaptic честно отказывается, без исключений."""
    from wheelscript.rumble import WheelHaptic, player_index
    sdl, inp = real
    idx, iid = virtual(sdl, inp)
    inp.poll()
    j = find(inp.scan(), iid)
    h = WheelHaptic()
    assert not h.attach(sdl, [j])
    assert player_index(sdl, j) is None or 0 <= player_index(sdl, j) <= 3
    sdl.SDL_JoystickDetachVirtual(idx)
