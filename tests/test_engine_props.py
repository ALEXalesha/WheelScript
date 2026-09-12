"""Инварианты движка маппинга (property-based, hypothesis)."""

import math

from hypothesis import assume, given
from hypothesis import strategies as st

from wheelscript.engine import (MAX_DT, NEUTRAL_PAD, TAP_SECONDS, DeviceState, Engine, binding_value,
                                read_source, release_level, shape)
from wheelscript.model import MOUSE_BUTTONS, PRESS_MODES, Action, Binding, InputSource, Profile

from .strategies import (DEV, N_AXES, N_BUTTONS, FakeOS, actions_no_toggle, bindings, digital_sources, dts,
                         good_axis, profiles, sources, states, weird_dts)

steps = st.lists(st.tuples(states(), dts), max_size=30)


def run(engine, os_, seq):
    for s, dt in seq:
        os_.apply(engine.step(s, dt, DEV))
        assert os_.keys == engine.held_keys()
        assert os_.buttons == engine.held_buttons()
        assert os_.pad.buttons == engine.held_pads()
        assert os_.pad == engine.pad_state


@given(profiles(), steps, st.booleans())
def test_events_balanced_and_mirror_engine_state(profile, seq, enabled):
    """Нет двойных нажатий/отпусканий, модель ОС всегда совпадает с тем, что движок считает зажатым."""
    e, os_ = Engine(profile, enabled=enabled), FakeOS()
    run(e, os_, seq)
    os_.apply(e.release_all())
    assert os_.keys == set() and os_.buttons == set() and os_.pad == NEUTRAL_PAD
    assert e.held_keys() == frozenset() and e.held_buttons() == frozenset() and e.held_pads() == frozenset()


@given(profiles(), steps)
def test_disable_releases_everything(profile, seq):
    e, os_ = Engine(profile, enabled=True), FakeOS()
    run(e, os_, seq)
    os_.apply(e.set_enabled(False))
    assert not e.enabled
    assert os_.keys == set() and os_.buttons == set()
    assert os_.pad == NEUTRAL_PAD, "выключение возвращает геймпад в нейтраль"


@given(profiles(bindings(action=actions_no_toggle)), steps)
def test_disabled_engine_is_silent(profile, seq):
    e = Engine(profile, enabled=False)
    for s, dt in seq:
        assert e.step(s, dt, DEV) == []
    assert e.release_all() == []


@given(profiles(), steps)
def test_not_enabled_implies_nothing_held(profile, seq):
    e, os_ = Engine(profile, enabled=True), FakeOS()
    for s, dt in seq:
        os_.apply(e.step(s, dt, DEV))
        if not e.enabled:
            assert os_.keys == set() and os_.buttons == set() and os_.pad == NEUTRAL_PAD


@given(profiles(bindings(action=actions_no_toggle)), steps)
def test_device_gone_releases_all_but_latched(profile, seq):
    """Руль отключили: через TAP_SECONDS не должно остаться зажатым ничего, кроме «залипших» клавиш."""
    e, os_ = Engine(profile, enabled=True), FakeOS()
    run(e, os_, seq)
    for _ in range(int(TAP_SECONDS / 0.01) + 2):
        os_.apply(e.step({}, 0.01, DEV))
    allowed_keys, allowed_buttons, allowed_pads = set(), set(), set()
    for b in profile.bindings:
        if b.action.press == "toggle":
            allowed_keys |= set(b.action.keys)
            if b.action.kind == "mouse_button":
                allowed_buttons.add(b.action.button)
            if b.action.kind == "pad_button":
                allowed_pads.add(b.action.pad)
    assert os_.keys <= allowed_keys
    assert os_.buttons <= allowed_buttons
    assert os_.pad.buttons <= allowed_pads
    assert (os_.pad.lx, os_.pad.ly, os_.pad.rx, os_.pad.ry, os_.pad.lt, os_.pad.rt) == (0,) * 6, \
        "без руля стики и курки в нейтрали"


@given(profiles(bindings(action=actions_no_toggle)),
       st.lists(st.tuples(states(axis=st.none()), dts), max_size=10))
def test_unknown_axes_never_trigger_axis_bindings(profile, seq):
    """Ось, которая ещё не двигалась (None), не должна срабатывать даже с инверсией."""
    axis_only = Profile(profile.name, tuple(b for b in profile.bindings if b.source.kind == "axis"))
    e = Engine(axis_only, enabled=True)
    for s, dt in seq:
        assert e.step(s, dt, DEV) == []


@given(profiles(), st.lists(st.tuples(states(), weird_dts), max_size=20))
def test_move_and_wheel_are_bounded(profile, seq):
    e, os_ = Engine(profile, enabled=True), FakeOS()
    move_budget = sum(b.action.speed for b in profile.bindings if b.action.kind == "mouse_move")
    wheel_budget = sum(b.action.speed for b in profile.bindings if b.action.kind == "mouse_wheel")
    for s, dt in seq:
        for ev in os_.apply(e.step(s, dt, DEV)):
            if ev[0] == "move":
                assert abs(ev[1]) <= move_budget * MAX_DT + 1
                assert abs(ev[2]) <= move_budget * MAX_DT + 1
            if ev[0] == "wheel":
                assert abs(ev[1]) // 120 <= wheel_budget * MAX_DT + 1


@given(good_axis, st.floats(1, 5000), st.floats(0, 0.9), st.floats(0.2, 5),
       st.integers(1, 200), st.floats(0.001, MAX_DT))
def test_accumulator_has_no_drift(v, speed, dz, curve, n, dt):
    """Сумма целых сдвигов мыши отличается от идеальной дробной суммы меньше чем на 1 пиксель."""
    b = Binding.make("x", InputSource.axis(0, "full", DEV), Action.move("right", speed), deadzone=dz, curve=curve)
    e = Engine(Profile("p", (b,)), enabled=True)
    s = {DEV: DeviceState((v,), (), ())}
    total = 0
    for _ in range(n):
        for ev in e.step(s, dt, DEV):
            if ev[0] == "move":
                total += ev[1]
    m = shape(abs(v), dz, curve) * (1 if v >= 0 else -1)
    ideal = m * speed * dt * n
    assert abs(total - ideal) < 1 + 1e-6 * max(1.0, abs(ideal))


@given(good_axis, st.floats(1, 5000), st.lists(dts, max_size=40), st.sampled_from(["left", "right", "up", "down"]))
def test_full_axis_is_symmetric(v, speed, dt_seq, direction):
    b = Binding.make("x", InputSource.axis(0, "full", DEV), Action.move(direction, speed), deadzone=0.0)
    a, c = Engine(Profile("p", (b,)), True), Engine(Profile("p", (b,)), True)
    for dt in dt_seq:
        ea = [ev for ev in a.step({DEV: DeviceState((v,))}, dt, DEV) if ev[0] == "move"]
        ec = [ev for ev in c.step({DEV: DeviceState((-v,))}, dt, DEV) if ev[0] == "move"]
        assert [(-x, -y) for _, x, y in ea] == [(x, y) for _, x, y in ec]


@given(st.floats(allow_nan=True, allow_infinity=True), st.floats(0, 0.95), st.floats(0.2, 5))
def test_shape_range(mag, dz, curve):
    r = shape(mag, dz, curve)
    assert 0.0 <= r <= 1.0 and not math.isnan(r)


@given(st.floats(0, 1), st.floats(0, 1), st.floats(0, 0.95), st.floats(0.2, 5))
def test_shape_monotonic_in_magnitude(a, b, dz, curve):
    lo, hi = sorted((a, b))
    assert shape(lo, dz, curve) <= shape(hi, dz, curve)


@given(st.floats(0, 1), st.floats(0, 0.95), st.floats(0, 0.95), st.floats(0.2, 5))
def test_shape_monotonic_in_deadzone(m, d1, d2, curve):
    lo, hi = sorted((d1, d2))
    assert shape(m, hi, curve) <= shape(m, lo, curve) + 1e-12


@given(st.floats(0, 0.95), st.floats(0.2, 5))
def test_shape_edges(dz, curve):
    assert shape(dz, dz, curve) == 0.0
    assert shape(0.0, dz, curve) == 0.0
    assert shape(1.0, dz, curve) == 1.0


@given(sources, states())
def test_read_source_range(src, s):
    for default in (DEV, None, "ghost"):
        v = read_source(src, s, default)
        if v is None:
            continue
        assert not math.isnan(v)
        if src.kind == "axis" and src.mode == "full":
            assert -1.0 <= v <= 1.0
        else:
            assert 0.0 <= v <= 1.0


@given(sources, states())
def test_read_source_none_when_device_missing(src, s):
    if src.device and src.device not in s:
        assert read_source(src, s, DEV) is None
    if not src.device and DEV not in s:
        assert read_source(src, s, DEV) is None


@given(bindings(), states())
def test_invert_is_involution(b, s):
    """Двойная инверсия возвращает исходное значение."""
    v = binding_value(b, s, DEV)
    inv = Binding.from_dict(b.to_dict() | {"invert": not b.invert})
    w = binding_value(inv, s, DEV)
    assert (v is None) == (w is None)
    if v is not None:
        base = read_source(b.source, s, DEV)
        signed = b.source.kind == "axis" and b.source.mode == "full"
        flipped = -base if signed else 1.0 - base
        assert {v, w} <= {base, flipped}
        assert math.isclose(v, flipped if b.invert else base)


@given(st.floats(0.01, 0.99), st.lists(st.floats(0, 1), min_size=1, max_size=60))
def test_hysteresis_matches_schmitt_trigger(thr, values):
    b = Binding.make("x", InputSource.axis(0, "pos", DEV), Action.key(["w"]), threshold=thr)
    e, os_ = Engine(Profile("p", (b,)), True), FakeOS()
    state = False
    for v in values:
        os_.apply(e.step({DEV: DeviceState((v,))}, 0.01, DEV))
        state = v >= release_level(thr) if state else v >= thr
        assert ("w" in os_.keys) == state


@given(st.lists(st.tuples(st.booleans(), st.booleans()), max_size=60))
def test_refcount_two_bindings_same_key(presses):
    """W зажата, пока зажата хотя бы одна из двух кнопок."""
    p = Profile("p", (Binding.make("a", InputSource.button(0, DEV), Action.key(["w"])),
                      Binding.make("b", InputSource.button(1, DEV), Action.key(["w", "shift"]))))
    e, os_ = Engine(p, True), FakeOS()
    for b0, b1 in presses:
        os_.apply(e.step({DEV: DeviceState((), (b0, b1), ())}, 0.01, DEV))
        assert ("w" in os_.keys) == (b0 or b1)
        assert ("shift" in os_.keys) == b1


@given(st.lists(st.booleans(), max_size=80))
def test_latch_mode_flips_on_each_press(presses):
    p = Profile("p", (Binding.make("a", InputSource.button(0, DEV), Action.key(["shift"], "toggle")),))
    e, os_ = Engine(p, True), FakeOS()
    prev, rising = False, 0
    for pressed in presses:
        os_.apply(e.step({DEV: DeviceState((), (pressed,), ())}, 0.01, DEV))
        rising += pressed and not prev
        prev = pressed
        assert ("shift" in os_.keys) == (rising % 2 == 1)


@given(st.lists(st.tuples(st.booleans(), st.floats(0.0, 0.04)), max_size=60))
def test_tap_every_press_is_one_tap_of_min_length(seq):
    """Каждое нажатие даёт ровно одно нажатие клавиши длиной >= TAP_SECONDS; быстрые повторы не теряются."""
    p = Profile("p", (Binding.make("a", InputSource.button(0, DEV), Action.key(["e"], "tap")),))
    e, os_ = Engine(p, True), FakeOS()
    held_for, prev, rising = 0.0, False, 0
    flush = [(False, 0.01)] * 200
    for pressed, dt in list(seq) + flush:
        was_down = "e" in os_.keys
        os_.apply(e.step({DEV: DeviceState((), (pressed,), ())}, dt, DEV))
        rising += pressed and not prev
        prev = pressed
        if "e" in os_.keys:
            held_for = 0.0 if not was_down else held_for + dt
            assert held_for <= TAP_SECONDS + 0.04 + 1e-9
        elif was_down:
            assert held_for + dt >= TAP_SECONDS - 1e-9, "тап короче минимума"
    assert "e" not in os_.keys
    assert len(os_.downs) == rising, "ни одно нажатие не потеряно и не задвоено"


@given(st.lists(st.booleans(), max_size=60), st.booleans())
def test_toggle_action_parity(presses, start):
    p = Profile("p", (Binding.make("t", InputSource.button(0, DEV), Action.toggle()),
                      Binding.make("w", InputSource.button(1, DEV), Action.key(["w"]))))
    e, os_ = Engine(p, start), FakeOS()
    prev, rising = False, 0
    for pressed in presses:
        os_.apply(e.step({DEV: DeviceState((), (pressed, True), ())}, 0.01, DEV))
        rising += pressed and not prev
        prev = pressed
        assert e.enabled == (start ^ (rising % 2 == 1))
        assert ("w" in os_.keys) == e.enabled


pressing_actions = st.one_of(
    st.builds(Action.key, st.lists(st.sampled_from(["w", "s", "e", "shift", "up"]), min_size=1, max_size=3),
              st.sampled_from(PRESS_MODES)),
    st.builds(Action.mouse, st.sampled_from(MOUSE_BUTTONS), st.sampled_from(PRESS_MODES)),
)


@given(digital_sources, pressing_actions, st.integers(1, 20))
def test_block_active_waits_for_release(src, action, hold_steps):
    b = Binding.make("x", src, action, threshold=0.5)
    e, os_ = Engine(Profile("p", (b,)), True), FakeOS()
    pressed_state = {DEV: DeviceState((1.0,) * N_AXES, (True,) * N_BUTTONS, ((1, 1),))}
    released_state = {DEV: DeviceState((-1.0,) * N_AXES, (False,) * N_BUTTONS, ((0, 0),))}
    v_pressed = binding_value(b, pressed_state, DEV)
    v_released = binding_value(b, released_state, DEV)
    assume(v_pressed is not None and abs(v_pressed) >= 0.5)
    assume(v_released is not None and abs(v_released) < release_level(0.5))
    e.block_active(pressed_state, DEV)
    for _ in range(hold_steps):
        os_.apply(e.step(pressed_state, 0.01, DEV))
        assert os_.keys == set() and os_.buttons == set()
    os_.apply(e.step(released_state, 0.01, DEV))
    os_.apply(e.step(pressed_state, 0.01, DEV))
    assert os_.keys or os_.buttons, "после отпускания и повторного нажатия привязка снова работает"


@given(profiles(), steps, profiles())
def test_set_profile_releases_old_outputs(p1, seq, p2):
    e, os_ = Engine(p1, True), FakeOS()
    run(e, os_, seq)
    os_.apply(e.set_profile(p2))
    assert os_.keys == set() and os_.buttons == set()
    assert e.bindings == p2.bindings


@given(profiles(), st.lists(st.tuples(states(), weird_dts), max_size=20))
def test_weird_dt_never_crashes(profile, seq):
    e, os_ = Engine(profile, True), FakeOS()
    for s, dt in seq:
        os_.apply(e.step(s, dt, DEV))


@given(profiles(), steps, st.sampled_from([None, "ghost", DEV]))
def test_default_device_variants(profile, seq, default):
    e, os_ = Engine(profile, True), FakeOS()
    for s, dt in seq:
        os_.apply(e.step(s, dt, default))
    os_.apply(e.release_all())
    assert os_.keys == set()


@given(good_axis, st.floats(0, 0.9), st.floats(0.2, 5), st.sampled_from(["left", "right", "up", "down"]),
       st.sampled_from(["left", "right"]))
def test_pad_stick_follows_wheel_exactly(v, dz, curve, direction, stick):
    """Стик повторяет руль: значение = shape(|v|) со знаком, в нужной оси, в нужную сторону (XInput: +Y вверх)."""
    b = Binding.make("s", InputSource.axis(0, "full", DEV), Action.stick(stick, direction), deadzone=dz, curve=curve)
    e, os_ = Engine(Profile("p", (b,)), True), FakeOS()
    os_.apply(e.step({DEV: DeviceState((v,))}, 0.01, DEV))
    m = shape(abs(v), dz, curve) * (1 if v >= 0 else -1)
    vx, vy = {"left": (-1, 0), "right": (1, 0), "up": (0, 1), "down": (0, -1)}[direction]
    x, y = (os_.pad.lx, os_.pad.ly) if stick == "left" else (os_.pad.rx, os_.pad.ry)
    other = (os_.pad.rx, os_.pad.ry) if stick == "left" else (os_.pad.lx, os_.pad.ly)
    assert math.isclose(x, vx * m, abs_tol=1e-12) and math.isclose(y, vy * m, abs_tol=1e-12)
    assert other == (0.0, 0.0)


@given(st.lists(st.tuples(good_axis, st.sampled_from(["left", "right", "up", "down"])), min_size=1, max_size=6))
def test_pad_stick_sum_is_clamped(parts):
    """Несколько привязок на один стик складываются, но никогда не выходят за [-1, 1]."""
    bs = tuple(Binding.make(f"s{i}", InputSource.axis(i % 4, "full", DEV), Action.stick("left", d), deadzone=0.0)
               for i, (_, d) in enumerate(parts))
    axes = [0.0] * 4
    for i, (v, _) in enumerate(parts):
        axes[i % 4] = v
    e, os_ = Engine(Profile("p", bs), True), FakeOS()
    os_.apply(e.step({DEV: DeviceState(tuple(axes))}, 0.01, DEV))
    assert -1.0 <= os_.pad.lx <= 1.0 and -1.0 <= os_.pad.ly <= 1.0


@given(st.lists(st.tuples(st.floats(-1, 1), st.sampled_from(["lt", "rt"])), min_size=1, max_size=4))
def test_pad_trigger_is_max_of_bindings(parts):
    bs = tuple(Binding.make(f"t{i}", InputSource.axis(i, "pedal", DEV), Action.trigger(w), deadzone=0.0)
               for i, (_, w) in enumerate(parts))
    axes = tuple(v for v, _ in parts)
    e, os_ = Engine(Profile("p", bs), True), FakeOS()
    os_.apply(e.step({DEV: DeviceState(axes)}, 0.01, DEV))
    for which in ("lt", "rt"):
        vals = [(v + 1) / 2 for v, w in parts if w == which]
        want = max(vals) if vals else 0.0
        got = os_.pad.lt if which == "lt" else os_.pad.rt
        assert math.isclose(got, want, abs_tol=1e-12)


@given(st.lists(st.tuples(st.booleans(), st.booleans()), max_size=40))
def test_pad_button_refcount(presses):
    """Кнопка A геймпада зажата, пока зажата хотя бы одна из двух кнопок руля; события только при изменении."""
    p = Profile("p", (Binding.make("a", InputSource.button(0, DEV), Action.pad_button("a")),
                      Binding.make("b", InputSource.button(1, DEV), Action.pad_button("a"))))
    e, os_ = Engine(p, True), FakeOS()
    changes, prev = 0, False
    for b0, b1 in presses:
        os_.apply(e.step({DEV: DeviceState((), (b0, b1), ())}, 0.01, DEV))
        assert ("a" in os_.pad.buttons) == (b0 or b1)
        changes += (b0 or b1) != prev
        prev = b0 or b1
    assert os_.pad_events == changes


@given(st.floats(0.01, 0.99))
def test_release_level_below_threshold(thr):
    r = release_level(thr)
    assert 0 < r < thr


def test_default_profile_on_resting_pxn_pedals_holds_nothing():
    """Регрессия: SDL до первого движения отдаёт 0.0 → педаль в режиме pedal = 50% → W зажата сама."""
    from wheelscript.model import default_profile
    e, os_ = Engine(default_profile(), True), FakeOS()
    before = {DEV: DeviceState((None,) * 7, (False,) * 54, ((0, 0),))}
    os_.apply(e.step(before, 0.01, DEV))
    assert os_.keys == set() and os_.moves == []
    rest = {DEV: DeviceState((0.0, None, -1.0, -1.0, -1.0, -1.0, -1.0), (False,) * 54, ((0, 0),))}
    os_.apply(e.step(rest, 0.01, DEV))
    assert os_.keys == set() and os_.moves == []
    gas = {DEV: DeviceState((0.0, None, 1.0, -1.0, -1.0, -1.0, -1.0), (False,) * 54, ((0, 0),))}
    os_.apply(e.step(gas, 0.01, DEV))
    assert os_.keys == {"w"}
