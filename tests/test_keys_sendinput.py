"""Таблица клавиш и бинарный формат SendInput (сам SendInput не вызывается)."""

import ctypes
import struct

from hypothesis import given
from hypothesis import strategies as st

from wheelscript import keys, sendinput


def test_every_key_has_vk_and_display():
    for name in keys.KEY_NAMES:
        code = keys.vk(name)
        assert isinstance(code, int) and 0 < code < 256
        assert keys.display(name)
        back = keys.name_of_vk(code)
        assert back is not None and keys.vk(back) == code


def test_scan_codes_unique():
    """Два разных имени с одним scan-кодом означали бы, что одна клавиша шлёт другую."""
    seen = {}
    for name in keys.KEY_NAMES:
        sc = keys.scan(name)
        if sc is None:
            continue
        assert sc not in seen, f"{name} и {seen[sc]} шлют один scan-код {sc}"
        seen[sc] = name


def test_wasd_physical_scan_codes():
    assert keys.scan("w") == (0x11, False)
    assert keys.scan("a") == (0x1E, False)
    assert keys.scan("s") == (0x1F, False)
    assert keys.scan("d") == (0x20, False)


def test_arrows_are_extended():
    for name in ("up", "down", "left", "right", "home", "end", "insert", "delete", "pageup", "pagedown",
                 "rctrl", "ralt", "num/"):
        assert keys.scan(name)[1] is True, name


@given(st.lists(st.one_of(st.sampled_from(keys.KEY_NAMES), st.text(max_size=6), st.none(), st.integers())))
def test_normalize_combo(names):
    combo = keys.normalize_combo(names)
    assert keys.normalize_combo(combo) == combo
    assert len(combo) == len(set(combo)) <= 4
    assert all(keys.is_key(n) for n in combo)
    mods = [n in keys.MODIFIERS for n in combo]
    assert mods == sorted(mods, reverse=True), "модификаторы идут первыми"


@given(st.integers(-10, 70000), st.integers(-5, 0x200), st.booleans())
def test_from_native_never_crashes(code, scan, ext):
    name = keys.from_native(code, scan, ext)
    assert name is None or keys.is_key(name)


def test_from_native_sides():
    assert keys.from_native(0x10, 0x2A) == "shift"
    assert keys.from_native(0x10, 0x36) == "rshift"
    assert keys.from_native(0x11, 0x1D, True) == "rctrl"
    assert keys.from_native(0x57, 0x11) == "w"


def test_struct_sizes_match_winapi():
    ptr = ctypes.sizeof(ctypes.c_void_p)
    assert ctypes.sizeof(sendinput.INPUT) == (40 if ptr == 8 else 28)
    assert ctypes.sizeof(sendinput.MOUSEINPUT) == (32 if ptr == 8 else 24)
    assert ctypes.sizeof(sendinput.KEYBDINPUT) == (24 if ptr == 8 else 16)


@given(st.sampled_from(keys.KEY_NAMES), st.booleans())
def test_key_input_flags(name, down):
    inp = sendinput.key_input(name, down)
    ki = inp.union.ki
    assert inp.type == sendinput.INPUT_KEYBOARD
    assert bool(ki.dwFlags & sendinput.KEYEVENTF_KEYUP) == (not down)
    sc = keys.scan(name)
    if sc is None:
        assert ki.wVk == keys.vk(name) and not ki.dwFlags & sendinput.KEYEVENTF_SCANCODE
    else:
        assert ki.wScan == sc[0] and ki.dwFlags & sendinput.KEYEVENTF_SCANCODE
        assert bool(ki.dwFlags & sendinput.KEYEVENTF_EXTENDEDKEY) == sc[1]


@given(st.integers(-(2 ** 31), 2 ** 31 - 1))
def test_wheel_negative_delta_encoding(delta):
    inp = sendinput._mouse(data=delta, flags=sendinput.MOUSEEVENTF_WHEEL)
    raw = inp.union.mi.mouseData
    assert struct.unpack("<i", struct.pack("<I", raw))[0] == delta
