"""Виртуальный геймпад: формат отчёта XUSB и поведение без драйвера (без настоящего ViGEmBus)."""

import sys
import types

from hypothesis import given
from hypothesis import strategies as st

from wheelscript import gamepad
from wheelscript.engine import NEUTRAL_PAD, PadState
from wheelscript.model import PAD_BUTTONS

any_float = st.floats(allow_nan=True, allow_infinity=True)
pad_states = st.builds(PadState, st.frozensets(st.sampled_from(PAD_BUTTONS)),
                       any_float, any_float, any_float, any_float, any_float, any_float)


def test_bits_are_distinct_xinput_flags():
    bits = list(gamepad.BITS.values())
    assert len(set(bits)) == len(bits) == len(PAD_BUTTONS)
    assert all(b & (b - 1) == 0 for b in bits), "каждая кнопка — ровно один бит"
    assert set(gamepad.BITS) == set(PAD_BUTTONS)


@given(pad_states)
def test_report_values_fit_xusb_types(state):
    """Любое состояние (даже NaN/inf) влезает в WORD/BYTE/SHORT — никакого переполнения стика."""
    b, lt, rt, lx, ly, rx, ry = gamepad.report_values(state)
    assert 0 <= b <= 0xFFFF
    assert 0 <= lt <= 255 and 0 <= rt <= 255
    for v in (lx, ly, rx, ry):
        assert -32767 <= v <= 32767


@given(st.floats(-1, 1), st.floats(-1, 1))
def test_report_axis_sign_and_monotonic(a, c):
    va = gamepad.report_values(PadState(lx=a))[3]
    vc = gamepad.report_values(PadState(lx=c))[3]
    assert (va > 0) <= (a > 0) and (va < 0) <= (a < 0)
    if a <= c:
        assert va <= vc


def test_neutral_report_is_zero():
    assert gamepad.report_values(NEUTRAL_PAD) == (0, 0, 0, 0, 0, 0, 0)
    full = PadState(frozenset(PAD_BUTTONS), 1, 1, -1, -1, 1, 1)
    assert gamepad.report_values(full) == (0xFFFF & sum(gamepad.BITS.values()), 255, 255, 32767, 32767, -32767, -32767)


def test_without_driver_reports_status_and_does_not_raise(monkeypatch):
    fake = types.ModuleType("vgamepad")

    class Boom:
        def __init__(self):
            raise Exception("VIGEM_ERROR_BUS_NOT_FOUND")
    fake.VX360Gamepad = Boom
    monkeypatch.setitem(sys.modules, "vgamepad", fake)
    seen = []
    pad = gamepad.VirtualPad(seen.append)
    pad.apply(PadState(frozenset({"a"})))
    pad.apply(PadState(frozenset({"b"})))  # повтор раньше RETRY не должен дёргать драйвер снова
    assert not pad.connected
    assert seen == ["недоступен: не установлен драйвер ViGEmBus"]
    pad.close()


def test_with_fake_driver_writes_report(monkeypatch):
    fake = types.ModuleType("vgamepad")
    updates = []

    class Report:
        wButtons = bLeftTrigger = bRightTrigger = sThumbLX = sThumbLY = sThumbRX = sThumbRY = 0

    class Pad:
        def __init__(self):
            self.report = Report()

        def update(self):
            r = self.report
            updates.append((r.wButtons, r.bLeftTrigger, r.bRightTrigger, r.sThumbLX, r.sThumbLY, r.sThumbRX,
                            r.sThumbRY))

        def reset(self):
            self.report = Report()
    fake.VX360Gamepad = Pad
    monkeypatch.setitem(sys.modules, "vgamepad", fake)
    seen = []
    pad = gamepad.VirtualPad(seen.append)
    state = PadState(frozenset({"a", "dup"}), lx=0.5, rt=1.0)
    pad.apply(state)
    assert pad.connected and seen == ["подключён (Xbox 360)"]
    assert updates[-1] == gamepad.report_values(state)
    pad.close()
    assert updates[-1] == (0, 0, 0, 0, 0, 0, 0), "при закрытии геймпад возвращается в нейтраль"
    assert not pad.connected
