"""Инварианты определения ввода «кликни поле — нажми на руле»."""

from hypothesis import assume, given
from hypothesis import strategies as st

from wheelscript.capture import AXIS_THRESHOLD, PEDAL_REST, Capture, adapt_source
from wheelscript.engine import DeviceState
from wheelscript.model import ACTION_KINDS, InputSource

from .strategies import DEV, N_AXES, N_BUTTONS, device_states, good_axis, sources, states

known_axis = st.one_of(st.none(), good_axis)


@given(states(axis=known_axis))
def test_no_change_no_detection(s):
    c = Capture(s)
    for _ in range(3):
        assert c.feed(s) is None


@given(device_states(axis=known_axis), st.integers(0, N_BUTTONS - 1))
def test_new_button_press_is_detected(base, i):
    assume(not base.buttons[i])
    assume(not any(base.buttons[:i]))
    c = Capture({DEV: base})
    buttons = list(base.buttons)
    buttons[i] = True
    found = c.feed({DEV: DeviceState(base.axes, tuple(buttons), base.hats)})
    assert found == InputSource.button(i, DEV)


@given(device_states(axis=known_axis), st.integers(0, N_BUTTONS - 1), st.integers(1, 5))
def test_button_held_at_start_needs_release(base, i, n):
    buttons = list(base.buttons)
    buttons[i] = True
    held = DeviceState(base.axes, tuple(buttons), base.hats)
    c = Capture({DEV: held})
    for _ in range(n):
        assert c.feed({DEV: held}) is None
    buttons[i] = False
    released = DeviceState(base.axes, tuple(buttons), base.hats)
    first = c.feed({DEV: released})
    assert first is None or first.kind == "button"
    assert c.feed({DEV: held}) == InputSource.button(i, DEV)


@given(st.lists(good_axis, min_size=N_AXES, max_size=N_AXES),
       st.lists(st.floats(-AXIS_THRESHOLD * 0.99, AXIS_THRESHOLD * 0.99), min_size=N_AXES, max_size=N_AXES))
def test_small_axis_noise_ignored(base, noise):
    b = DeviceState(tuple(base), (False,) * N_BUTTONS, ((0, 0),))
    moved = tuple(max(-1.0, min(1.0, v + d)) for v, d in zip(base, noise))
    c = Capture({DEV: b})
    assert c.feed({DEV: DeviceState(moved, b.buttons, b.hats)}) is None


@given(st.integers(0, N_AXES - 1), good_axis, good_axis)
def test_axis_detection_and_mode(i, rest, target):
    assume(abs(target - rest) >= AXIS_THRESHOLD)
    axes = [0.0] * N_AXES
    axes[i] = rest
    c = Capture({DEV: DeviceState(tuple(axes))})
    axes2 = list(axes)
    axes2[i] = target
    found = c.feed({DEV: DeviceState(tuple(axes2))})
    assert found is not None and found.kind == "axis" and found.index == i and found.device == DEV
    if rest <= -PEDAL_REST:
        assert found.mode == "pedal"
    elif rest >= PEDAL_REST:
        assert found.mode == "pedal_inv"
    else:
        assert found.mode == ("pos" if target > rest else "neg")


@given(st.integers(0, N_AXES - 1), good_axis)
def test_unknown_axis_first_value_is_not_a_press(i, first):
    """Регрессия PXN: педаль «прыгает» из None в -1 при первом HID-отчёте — это не нажатие."""
    axes = [None] * N_AXES
    c = Capture({DEV: DeviceState(tuple(axes))})
    axes[i] = first
    assert c.feed({DEV: DeviceState(tuple(axes))}) is None


def test_pxn_pedal_flow():
    c = Capture({DEV: DeviceState((None,) * 7)})
    rest = (0.0, None, -1.0, -1.0, -1.0, -1.0, -1.0)
    assert c.feed({DEV: DeviceState(rest)}) is None
    pressed = (0.0, None, 0.8, -1.0, -1.0, -1.0, -1.0)
    assert c.feed({DEV: DeviceState(pressed)}) == InputSource.axis(2, "pedal", DEV)


@given(st.tuples(st.integers(-1, 1), st.integers(-1, 1)), st.tuples(st.integers(-1, 1), st.integers(-1, 1)))
def test_hat_detection_direction_consistent(base, now):
    c = Capture({DEV: DeviceState((), (), (base,))})
    found = c.feed({DEV: DeviceState((), (), (now,))})
    if found is None:
        return
    assert found.kind == "hat" and found.index == 0
    hx, hy = now
    assert {"up": hy > 0, "down": hy < 0, "left": hx < 0, "right": hx > 0}[found.mode]


@given(states(axis=known_axis), device_states(axis=known_axis))
def test_new_device_mid_capture_does_not_fire(s, newdev):
    c = Capture(s)
    s2 = dict(s)
    s2["late"] = newdev
    found = c.feed(s2)
    assert found is None or found.device != "late"


@given(states(axis=known_axis), st.lists(states(axis=known_axis), max_size=10))
def test_capture_result_is_canonical(base, seq):
    c = Capture(base)
    for s in seq:
        found = c.feed(s)
        if found is not None:
            assert InputSource.from_dict(found.to_dict()) == found
            assert found.device in s
            break


@given(sources, st.sampled_from(ACTION_KINDS))
def test_adapt_source(src, kind):
    a = adapt_source(src, kind)
    assert adapt_source(a, kind) == a
    if kind in ("mouse_move", "mouse_wheel") and src.kind == "axis" and src.mode in ("pos", "neg"):
        assert a.mode == "full" and a.index == src.index and a.device == src.device
    else:
        assert a == src
