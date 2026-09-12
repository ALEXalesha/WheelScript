"""Инварианты модели и разбора конфигов: любой мусор -> валидный канонический объект."""

import json

from hypothesis import given
from hypothesis import strategies as st

from wheelscript import keys
from wheelscript.model import (ACTION_KINDS, AXIS_MODES, CURVE, DEADZONE, DIRECTIONS, HAT_DIRS, MAX_BINDINGS,
                               MAX_COMBO, MAX_NAME, MAX_PROFILES, MOUSE_BUTTONS, MOVE_SPEED, PRESS_MODES,
                               SOURCE_KINDS, THRESHOLD, TICK_RATE, WHEEL_SPEED, Action, Binding, Config,
                               InputSource, Profile, Settings, clean_text, default_config, default_profile,
                               unique_name)

from .strategies import bindings, configs, json_values, junk_action, junk_binding, junk_config, junk_source

anything = st.one_of(json_values, junk_config())


def check_source(s: InputSource):
    assert s.kind in SOURCE_KINDS
    assert 0 <= s.index <= 255 and isinstance(s.index, int)
    if s.kind == "axis":
        assert s.mode in AXIS_MODES
    elif s.kind == "hat":
        assert s.mode in HAT_DIRS
    else:
        assert s.mode == ""
    if s.kind == "none":
        assert s == InputSource()


def check_action(a: Action):
    assert a.kind in ACTION_KINDS
    assert a.button in MOUSE_BUTTONS and a.direction in DIRECTIONS and a.press in PRESS_MODES
    assert keys.normalize_combo(a.keys) == a.keys and len(a.keys) <= MAX_COMBO
    if a.kind == "mouse_move":
        assert MOVE_SPEED[0] <= a.speed <= MOVE_SPEED[1]
    if a.kind == "mouse_wheel":
        assert WHEEL_SPEED[0] <= a.speed <= WHEEL_SPEED[1]
    if a.kind != "key":
        assert a.keys == ()


def check_text(t: str):
    assert isinstance(t, str) and t and len(t) <= MAX_NAME
    assert t == t.strip() and all(ch.isprintable() for ch in t)


def check_binding(b: Binding):
    check_text(b.name)
    check_source(b.source)
    check_action(b.action)
    assert THRESHOLD[0] <= b.threshold <= THRESHOLD[1]
    assert DEADZONE[0] <= b.deadzone <= DEADZONE[1]
    assert CURVE[0] <= b.curve <= CURVE[1]
    assert isinstance(b.enabled, bool) and isinstance(b.invert, bool)


def check_config(c: Config):
    assert 1 <= len(c.profiles) <= MAX_PROFILES
    names = [p.name for p in c.profiles]
    assert len(set(names)) == len(names), "имена профилей уникальны"
    assert c.settings.active_profile in names
    assert c.active.name == c.settings.active_profile
    assert TICK_RATE[0] <= c.settings.tick_rate <= TICK_RATE[1]
    assert c.settings.toggle_key == "" or keys.is_key(c.settings.toggle_key)
    for p in c.profiles:
        check_text(p.name)
        assert len(p.bindings) <= MAX_BINDINGS
        for b in p.bindings:
            check_binding(b)


@given(st.one_of(anything, junk_source()))
def test_source_from_anything(d):
    s = InputSource.from_dict(d)
    check_source(s)
    assert InputSource.from_dict(s.to_dict()) == s


@given(st.one_of(anything, junk_action()))
def test_action_from_anything(d):
    a = Action.from_dict(d)
    check_action(a)
    assert Action.from_dict(a.to_dict()) == a


@given(st.one_of(anything, junk_binding()))
def test_binding_from_anything(d):
    b = Binding.from_dict(d)
    check_binding(b)
    assert Binding.from_dict(b.to_dict()) == b


@given(anything)
def test_config_from_anything(d):
    c = Config.from_dict(d)
    check_config(c)
    assert Config.from_dict(c.to_dict()) == c


@given(anything)
def test_config_survives_json_utf8(d):
    """Канонический конфиг всегда пишется в UTF-8 JSON (нет суррогатов, NaN, inf) и читается обратно."""
    c = Config.from_dict(d)
    text = json.dumps(c.to_dict(), ensure_ascii=False, allow_nan=False)
    text.encode("utf-8")
    assert Config.from_dict(json.loads(text)) == c


@given(configs)
def test_generated_configs_valid(c):
    check_config(c)


@given(bindings())
def test_generated_bindings_canonical(b):
    check_binding(b)
    assert Binding.from_dict(b.to_dict()) == b


@given(st.lists(st.text(max_size=90), max_size=10))
def test_duplicate_profile_names_are_made_unique(names):
    c = Config.from_dict({"profiles": [{"name": n, "bindings": []} for n in names]})
    check_config(c)


@given(st.text(max_size=100), st.sets(st.text(max_size=100), max_size=20))
def test_unique_name(name, taken):
    name = clean_text(name, "x")
    taken = {clean_text(t, "x") for t in taken}
    r = unique_name(name, taken)
    assert r not in taken and len(r) <= MAX_NAME


@given(st.text())
def test_clean_text(t):
    r = clean_text(t, "def")
    check_text(r)
    r.encode("utf-8")


@given(st.one_of(st.floats(allow_nan=True, allow_infinity=True), st.integers(), st.text(max_size=8),
                 st.booleans(), st.none()))
def test_numeric_fields_always_clamped(x):
    b = Binding.from_dict({"threshold": x, "deadzone": x, "curve": x, "action": {"kind": "mouse_move", "speed": x}})
    check_binding(b)
    s = Settings.from_dict({"tick_rate": x})
    assert TICK_RATE[0] <= s.tick_rate <= TICK_RATE[1]


def test_huge_int_does_not_crash():
    b = Binding.from_dict({"threshold": 10 ** 400, "source": {"kind": "button", "index": 10 ** 400}})
    check_binding(b)


def test_default_profile_and_config():
    p = default_profile()
    assert Profile.from_dict(p.to_dict()) == p
    for b in p.bindings:
        check_binding(b)
    check_config(default_config())
