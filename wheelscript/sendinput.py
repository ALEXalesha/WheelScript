"""
Обёртка над WinAPI SendInput.

Клавиши шлются scan-кодами: игры с raw input / DirectInput читают именно их
и игнорируют «виртуальные» нажатия. Стрелки, Home/End и т.п. — extended
клавиши, без флага KEYEVENTF_EXTENDEDKEY Windows примет их за цифры Numpad.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes

from . import keys

log = logging.getLogger(__name__)

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000

_BUTTON_FLAGS = {
    "left": (0x0002, 0x0004, 0),
    "right": (0x0008, 0x0010, 0),
    "middle": (0x0020, 0x0040, 0),
    "x1": (0x0080, 0x0100, 1),
    "x2": (0x0080, 0x0100, 2),
}

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    # HARDWAREINPUT нужен не сам по себе, а чтобы размер union совпадал с WinAPI.
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]


if sys.platform == "win32":
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    _user32.SendInput.restype = wintypes.UINT
    _user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
    _user32.GetAsyncKeyState.restype = ctypes.c_short
else:  # позволяет импортировать модуль (и гонять тесты) не на Windows
    _user32 = None

_warned = False


def _send(*inputs: INPUT) -> None:
    global _warned
    if _user32 is None or not inputs:
        return
    arr = (INPUT * len(inputs))(*inputs)
    sent = _user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
    if sent != len(inputs) and not _warned:
        _warned = True
        log.warning(
            "SendInput отправил %s из %s событий (ошибка %s). Если игра запущена "
            "от администратора, WheelScript тоже нужно запустить от администратора.",
            sent, len(inputs), ctypes.get_last_error(),
        )


def _mouse(dx: int = 0, dy: int = 0, data: int = 0, flags: int = 0) -> INPUT:
    mi = MOUSEINPUT(int(dx), int(dy), int(data) & 0xFFFFFFFF, flags, 0, 0)
    return INPUT(INPUT_MOUSE, _INPUTUNION(mi=mi))


def key_input(name: str, down: bool) -> INPUT:
    sc = keys.scan(name)
    if sc is not None:
        code, ext = sc
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if ext else 0)
        ki = KEYBDINPUT(0, code, flags | (0 if down else KEYEVENTF_KEYUP), 0, 0)
    else:
        ki = KEYBDINPUT(keys.vk(name) or 0, 0, 0 if down else KEYEVENTF_KEYUP, 0, 0)
    return INPUT(INPUT_KEYBOARD, _INPUTUNION(ki=ki))


def key(name: str, down: bool) -> None:
    if keys.is_key(name):
        _send(key_input(name, down))


def mouse_button(name: str, down: bool) -> None:
    flags = _BUTTON_FLAGS.get(name)
    if flags:
        _send(_mouse(data=flags[2], flags=flags[0] if down else flags[1]))


def mouse_move(dx: int, dy: int) -> None:
    if dx or dy:
        _send(_mouse(dx=dx, dy=dy, flags=MOUSEEVENTF_MOVE))


def mouse_wheel(delta: int, horizontal: bool = False) -> None:
    if delta:
        _send(_mouse(data=delta, flags=MOUSEEVENTF_HWHEEL if horizontal else MOUSEEVENTF_WHEEL))


def is_key_down(name: str) -> bool:
    code = keys.vk(name)
    if _user32 is None or code is None:
        return False
    return bool(_user32.GetAsyncKeyState(code) & 0x8000)


def apply(events) -> None:
    """Отправляет события движка (см. engine.py) в систему."""
    for ev in events:
        kind = ev[0]
        if kind == "key":
            key(ev[1], ev[2])
        elif kind == "mouse":
            mouse_button(ev[1], ev[2])
        elif kind == "move":
            mouse_move(ev[1], ev[2])
        elif kind == "wheel":
            mouse_wheel(ev[1], ev[2])
