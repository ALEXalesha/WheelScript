"""Разбор нажатий, которые присылает Qt (виртуальный код, скан-код, флаг extended)."""

import pytest

from wheelscript import keys

VK_SHIFT, VK_CONTROL, VK_MENU = 0x10, 0x11, 0x12


@pytest.mark.parametrize("vk, scan, ext, name", [
    (VK_SHIFT, 0x2A, False, "shift"), (VK_SHIFT, 0x36, False, "rshift"),
    (0xA0, 0x2A, False, "shift"), (0xA1, 0x36, False, "rshift"),
    (VK_CONTROL, 0x1D, False, "ctrl"), (VK_CONTROL, 0x1D, True, "rctrl"),
    (0xA2, 0x1D, False, "ctrl"), (0xA3, 0x1D, True, "rctrl"),
    (VK_MENU, 0x38, False, "alt"), (VK_MENU, 0x38, True, "ralt"),
    (0xA4, 0x38, False, "alt"), (0xA5, 0x38, True, "ralt"),
    (0x41, 0x1E, False, "a"), (0x70, 0x3B, False, "f1"), (0x26, 0x48, True, "up"),
    (0x2C, 0x37, True, "printscreen"), (0x5B, 0x5B, True, "win"),
])
def test_known_keys(vk, scan, ext, name):
    assert keys.from_native(vk, scan, ext) == name


def test_every_table_key_round_trips():
    # Каждая клавиша таблицы узнаётся по своим же кодам.
    for name in keys.KEY_NAMES:
        vk = keys.vk(name)
        sc = keys.scan(name)
        scan, ext = sc if sc else (0, False)
        got = keys.from_native(vk, scan, ext)
        assert got == name or keys.vk(got) == vk, (name, got)


@pytest.mark.parametrize("vk", [0, 0xFF, 0xE5, 0x07, 0x3A])
def test_unknown_codes(vk):
    assert keys.from_native(vk, 0, False) is None


def test_extended_flag_from_qt_modifiers():
    assert keys.is_extended(0x01000000) and keys.is_extended(0x01000003)
    assert not keys.is_extended(0) and not keys.is_extended(0x3)
