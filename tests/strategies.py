"""Общие генераторы данных для property-тестов."""

from hypothesis import strategies as st

from wheelscript.engine import DeviceState
from wheelscript.model import (ACTION_KINDS, AXIS_MODES, DIRECTIONS, HAT_DIRS, MOUSE_BUTTONS, PRESS_MODES,
                               SOURCE_KINDS, Action, Binding, Config, InputSource, Profile, Settings)

DEV = "dev0"
DEV2 = "dev1"
N_AXES, N_BUTTONS, N_HATS = 4, 6, 1
SMALL_KEYS = ["w", "a", "s", "d", "ctrl", "shift", "space", "e", "up", "f5"]

good_axis = st.floats(-1.0, 1.0, allow_nan=False)
weird_axis = st.one_of(st.none(), good_axis, st.floats(allow_nan=True, allow_infinity=True),
                       st.sampled_from([-1.0, 0.0, 1.0, -0.999, 1e-9]))
hat_value = st.tuples(st.integers(-1, 1), st.integers(-1, 1))


def device_states(axis=weird_axis, n_axes=N_AXES, n_buttons=N_BUTTONS, n_hats=N_HATS):
    return st.builds(
        DeviceState,
        axes=st.tuples(*([axis] * n_axes)),
        buttons=st.tuples(*([st.booleans()] * n_buttons)),
        hats=st.tuples(*([hat_value] * n_hats)),
    )


def states(axis=weird_axis):
    one = device_states(axis)
    return st.one_of(
        st.just({}),
        st.fixed_dictionaries({DEV: one}),
        st.fixed_dictionaries({DEV: one, DEV2: one}),
    )


devices = st.sampled_from(["", DEV, DEV2, "ghost"])
sources = st.one_of(
    st.just(InputSource()),
    st.builds(InputSource.axis, st.integers(0, 5), st.sampled_from(AXIS_MODES), devices),
    st.builds(InputSource.button, st.integers(0, 7), devices),
    st.builds(InputSource.hat, st.integers(0, 1), st.sampled_from(HAT_DIRS), devices),
)
digital_sources = st.one_of(
    st.builds(InputSource.button, st.integers(0, N_BUTTONS - 1), st.just(DEV)),
    st.builds(InputSource.hat, st.just(0), st.sampled_from(HAT_DIRS), st.just(DEV)),
    st.builds(InputSource.axis, st.integers(0, N_AXES - 1), st.sampled_from(AXIS_MODES), st.just(DEV)),
)

press = st.sampled_from(PRESS_MODES)
actions = st.one_of(
    st.builds(Action.key, st.lists(st.sampled_from(SMALL_KEYS), max_size=3), press),
    st.builds(Action.mouse, st.sampled_from(MOUSE_BUTTONS), press),
    st.builds(Action.move, st.sampled_from(DIRECTIONS), st.floats(0, 5000)),
    st.builds(Action.wheel, st.sampled_from(DIRECTIONS), st.floats(0, 50)),
    st.just(Action.toggle()),
    st.just(Action()),
)
actions_no_toggle = actions.filter(lambda a: a.kind != "toggle")

names = st.text(max_size=12)


def bindings(source=sources, action=actions):
    return st.builds(
        Binding.make,
        names, source, action,
        enabled=st.booleans(),
        threshold=st.floats(0.01, 0.99),
        deadzone=st.floats(0.0, 0.95),
        curve=st.floats(0.2, 5.0),
        invert=st.booleans(),
    )


def profiles(binding=None, max_size=8):
    binding = binding if binding is not None else bindings()
    return st.builds(Profile, names, st.lists(binding, max_size=max_size).map(tuple))


dts = st.one_of(st.floats(0, 0.05), st.sampled_from([0.0, 0.008, 0.016, 0.1, 5.0]))
weird_dts = st.one_of(dts, st.floats(allow_nan=True, allow_infinity=True))

json_values = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats() | st.text(max_size=20),
    lambda c: st.lists(c, max_size=5) | st.dictionaries(st.text(max_size=10), c, max_size=5),
    max_leaves=25,
)
junk = st.one_of(json_values, st.sampled_from(list(SOURCE_KINDS) + list(ACTION_KINDS) + list(AXIS_MODES)))


def junk_source():
    return st.fixed_dictionaries({}, optional={
        "kind": junk, "index": junk, "mode": junk, "device": junk})


def junk_action():
    return st.fixed_dictionaries({}, optional={
        "kind": junk, "keys": st.one_of(junk, st.lists(st.one_of(st.sampled_from(SMALL_KEYS), junk))),
        "button": junk, "direction": junk, "speed": junk, "press": junk})


def junk_binding():
    return st.fixed_dictionaries({}, optional={
        "name": junk, "source": st.one_of(junk, junk_source()), "action": st.one_of(junk, junk_action()),
        "enabled": junk, "threshold": junk, "deadzone": junk, "curve": junk, "invert": junk})


def junk_config():
    profile = st.fixed_dictionaries({}, optional={
        "name": st.one_of(junk, st.sampled_from(["A", "A", "B"])),
        "bindings": st.one_of(junk, st.lists(st.one_of(junk, junk_binding()), max_size=4))})
    settings_ = st.fixed_dictionaries({}, optional={
        "toggle_key": st.one_of(junk, st.sampled_from(SMALL_KEYS + ["", "f8"])), "tick_rate": junk,
        "start_enabled": junk, "active_profile": st.one_of(junk, st.sampled_from(["A", "B", "Z"])),
        "monitor_device": junk})
    return st.one_of(junk, st.fixed_dictionaries({}, optional={
        "settings": st.one_of(junk, settings_), "profiles": st.one_of(junk, st.lists(st.one_of(junk, profile),
                                                                                     max_size=5))}))


configs = st.builds(
    lambda ps, s: Config.from_dict({"settings": s.to_dict(), "profiles": [p.to_dict() for p in ps]}),
    st.lists(profiles(max_size=4), max_size=4),
    st.builds(Settings.from_dict, st.fixed_dictionaries({
        "toggle_key": st.sampled_from(SMALL_KEYS + ["", "f8"]), "tick_rate": st.integers(0, 2000),
        "start_enabled": st.booleans(), "active_profile": names})),
)


class FakeOS:
    """Модель ОС: строго проверяет, что события не нарушают состояние клавиатуры и мыши."""

    def __init__(self):
        self.keys: set[str] = set()
        self.buttons: set[str] = set()
        self.moves: list[tuple[int, int]] = []
        self.wheels: list[tuple[int, bool]] = []
        self.downs: list[str] = []

    def apply(self, events):
        from wheelscript import keys as keymod
        for ev in events:
            kind = ev[0]
            if kind == "key":
                _, name, down = ev
                assert keymod.is_key(name), name
                if down:
                    assert name not in self.keys, f"двойное нажатие {name}"
                    self.keys.add(name)
                    self.downs.append(name)
                else:
                    assert name in self.keys, f"отпускание без нажатия {name}"
                    self.keys.remove(name)
            elif kind == "mouse":
                _, name, down = ev
                assert name in MOUSE_BUTTONS
                if down:
                    assert name not in self.buttons, f"двойное нажатие мыши {name}"
                    self.buttons.add(name)
                else:
                    assert name in self.buttons, f"отпускание мыши без нажатия {name}"
                    self.buttons.remove(name)
            elif kind == "move":
                _, dx, dy = ev
                assert type(dx) is int and type(dy) is int
                assert dx or dy
                self.moves.append((dx, dy))
            elif kind == "wheel":
                _, delta, horizontal = ev
                assert type(delta) is int and delta != 0 and delta % 120 == 0
                assert isinstance(horizontal, bool)
                self.wheels.append((delta, horizontal))
            elif kind == "enabled":
                assert isinstance(ev[1], bool)
            else:
                raise AssertionError(f"неизвестное событие {ev!r}")
        return events
