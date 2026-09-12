"""Таблица клавиш: имя -> (virtual-key, scan code set 1, extended)."""

from __future__ import annotations

from typing import Iterable, Optional

_TABLE: dict[str, tuple[int, int, bool]] = {}


def _k(name: str, vk: int, scan: int, ext: bool = False) -> None:
    _TABLE[name] = (vk, scan, ext)


for _i, _ch in enumerate("1234567890"):
    _k(_ch, ord(_ch), 0x02 + _i)
for _row, _start in (("qwertyuiop", 0x10), ("asdfghjkl", 0x1E), ("zxcvbnm", 0x2C)):
    for _i, _ch in enumerate(_row):
        _k(_ch, ord(_ch.upper()), _start + _i)
for _i in range(10):
    _k(f"f{_i + 1}", 0x70 + _i, 0x3B + _i)
_k("f11", 0x7A, 0x57)
_k("f12", 0x7B, 0x58)
for _i in range(11):
    _k(f"f{_i + 13}", 0x7C + _i, 0x64 + _i)
_k("f24", 0x87, 0x76)

_k("esc", 0x1B, 0x01)
_k("minus", 0xBD, 0x0C)
_k("equals", 0xBB, 0x0D)
_k("backspace", 0x08, 0x0E)
_k("tab", 0x09, 0x0F)
_k("lbracket", 0xDB, 0x1A)
_k("rbracket", 0xDD, 0x1B)
_k("enter", 0x0D, 0x1C)
_k("ctrl", 0x11, 0x1D)
_k("rctrl", 0xA3, 0x1D, True)
_k("semicolon", 0xBA, 0x27)
_k("quote", 0xDE, 0x28)
_k("grave", 0xC0, 0x29)
_k("shift", 0x10, 0x2A)
_k("backslash", 0xDC, 0x2B)
_k("comma", 0xBC, 0x33)
_k("period", 0xBE, 0x34)
_k("slash", 0xBF, 0x35)
_k("rshift", 0xA1, 0x36)
_k("num*", 0x6A, 0x37)
_k("alt", 0x12, 0x38)
_k("ralt", 0xA5, 0x38, True)
_k("space", 0x20, 0x39)
_k("capslock", 0x14, 0x3A)
_k("numlock", 0x90, 0x45)
_k("scrolllock", 0x91, 0x46)
_k("num7", 0x67, 0x47)
_k("num8", 0x68, 0x48)
_k("num9", 0x69, 0x49)
_k("num-", 0x6D, 0x4A)
_k("num4", 0x64, 0x4B)
_k("num5", 0x65, 0x4C)
_k("num6", 0x66, 0x4D)
_k("num+", 0x6B, 0x4E)
_k("num1", 0x61, 0x4F)
_k("num2", 0x62, 0x50)
_k("num3", 0x63, 0x51)
_k("num0", 0x60, 0x52)
_k("num.", 0x6E, 0x53)
_k("num/", 0x6F, 0x35, True)
_k("home", 0x24, 0x47, True)
_k("up", 0x26, 0x48, True)
_k("pageup", 0x21, 0x49, True)
_k("left", 0x25, 0x4B, True)
_k("right", 0x27, 0x4D, True)
_k("end", 0x23, 0x4F, True)
_k("down", 0x28, 0x50, True)
_k("pagedown", 0x22, 0x51, True)
_k("insert", 0x2D, 0x52, True)
_k("delete", 0x2E, 0x53, True)
_k("win", 0x5B, 0x5B, True)
_k("rwin", 0x5C, 0x5C, True)
_k("apps", 0x5D, 0x5D, True)
_k("printscreen", 0x2C, 0x37, True)
# Pause в scan-кодах — многобайтовая последовательность, шлём через VK.
_k("pause", 0x13, 0)

KEY_NAMES: tuple[str, ...] = tuple(_TABLE)
_VK_TO_NAME: dict[int, str] = {}
for _name, (_vk, _s, _e) in _TABLE.items():
    _VK_TO_NAME.setdefault(_vk, _name)

MODIFIER_ORDER = ("ctrl", "rctrl", "shift", "rshift", "alt", "ralt", "win", "rwin")
MODIFIERS = frozenset(MODIFIER_ORDER)

_DISPLAY = {
    "esc": "Esc", "minus": "-", "equals": "=", "backspace": "Backspace", "tab": "Tab",
    "lbracket": "[", "rbracket": "]", "enter": "Enter", "ctrl": "Ctrl", "rctrl": "Правый Ctrl",
    "semicolon": ";", "quote": "'", "grave": "`", "shift": "Shift", "backslash": "\\",
    "comma": ",", "period": ".", "slash": "/", "rshift": "Правый Shift", "alt": "Alt",
    "ralt": "Правый Alt", "space": "Пробел", "capslock": "CapsLock", "numlock": "NumLock",
    "scrolllock": "ScrollLock", "home": "Home", "up": "↑", "pageup": "PageUp", "left": "←",
    "right": "→", "end": "End", "down": "↓", "pagedown": "PageDown", "insert": "Insert",
    "delete": "Delete", "win": "Win", "rwin": "Правый Win", "apps": "Menu",
    "printscreen": "PrintScreen", "pause": "Pause",
}


def is_key(name: object) -> bool:
    return isinstance(name, str) and name in _TABLE


def vk(name: str) -> Optional[int]:
    entry = _TABLE.get(name)
    return entry[0] if entry else None


def scan(name: str) -> Optional[tuple[int, bool]]:
    entry = _TABLE.get(name)
    if not entry or entry[1] == 0:
        return None
    return entry[1], entry[2]


def name_of_vk(code: int) -> Optional[str]:
    return _VK_TO_NAME.get(code)


def from_tk(keycode: int, keysym: str = "") -> Optional[str]:
    """На Windows tkinter отдаёт в event.keycode виртуальный код клавиши."""
    right = keysym.endswith("_R")
    if keycode == 0x10:
        return "rshift" if right else "shift"
    if keycode == 0x11:
        return "rctrl" if right else "ctrl"
    if keycode == 0x12:
        return "ralt" if right else "alt"
    if keycode in (0xA0, 0xA2, 0xA4):
        return {0xA0: "shift", 0xA2: "ctrl", 0xA4: "alt"}[keycode]
    return name_of_vk(keycode)


def display(name: str) -> str:
    if name in _DISPLAY:
        return _DISPLAY[name]
    if name.startswith("num") and len(name) > 3:
        return "Num " + name[3:]
    return name.upper()


def normalize_combo(names: Iterable[object], limit: int = 4) -> tuple[str, ...]:
    """Убирает мусор и дубли, модификаторы ставит вперёд в фиксированном порядке."""
    seen: list[str] = []
    for n in names:
        if isinstance(n, str):
            n = n.strip().lower()
        if is_key(n) and n not in seen:
            seen.append(n)
    mods = [m for m in MODIFIER_ORDER if m in seen]
    rest = [n for n in seen if n not in MODIFIERS]
    return tuple((mods + rest)[:limit])


def combo_text(names: Iterable[str]) -> str:
    names = tuple(names)
    return " + ".join(display(n) for n in names) if names else "—"
