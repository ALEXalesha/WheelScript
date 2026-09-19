"""Палитры тем: полнота, контраст текста, выбор «как в системе» (без окон)."""

import re

import pytest

from wheelscript import theme
from wheelscript.model import THEMES

HEX = re.compile(r"^#[0-9a-f]{6}$")

# (цвет текста, цвет фона, минимальный контраст по WCAG)
PAIRS = [
    ("fg", "bg", 7.0), ("text", "surface", 7.0), ("text", "surface2", 4.5),
    ("off", "bg", 4.5), ("entry_fg", "wait_bg", 4.5), ("fg", "live_bg", 4.5),
    ("on", "bg", 3.0), ("error", "bg", 3.0), ("faint", "surface", 3.0),
    ("faint", "surface2", 3.0),  # «ещё не двигалась» рисуется поверх полоски оси
    ("disabled", "surface", 3.0),  # выключенные привязки в таблице
]


def luminance(color: str) -> float:
    def ch(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_palettes_have_same_keys():
    assert set(theme.LIGHT) == set(theme.DARK)
    assert theme.DARK["dark"] is True and theme.LIGHT["dark"] is False


@pytest.mark.parametrize("pal", [theme.LIGHT, theme.DARK], ids=["light", "dark"])
def test_palette_is_all_hex(pal):
    for k, v in pal.items():
        if k != "dark":
            assert HEX.match(v), f"{k}={v!r}"


@pytest.mark.parametrize("pal", [theme.LIGHT, theme.DARK], ids=["light", "dark"])
@pytest.mark.parametrize("fg,bg,minimum", PAIRS)
def test_text_is_readable(pal, fg, bg, minimum):
    assert contrast(pal[fg], pal[bg]) >= minimum, f"{fg} на {bg}: {contrast(pal[fg], pal[bg]):.2f}"


def test_labels_cover_all_modes():
    assert set(theme.LABELS) == set(THEMES)


@pytest.mark.parametrize("mode, dark", [("dark", True), ("light", False), ("dark", True)])
def test_apply_switches_qt_and_palette(qapp, mode, dark):
    try:
        assert theme.apply(qapp, mode) is dark
        assert theme.P == (theme.DARK if dark else theme.LIGHT)
        assert theme.is_dark(qapp.palette()) is dark
    finally:
        theme.apply(qapp, "light")


def test_system_mode_follows_qt(qapp):
    from PySide6.QtCore import Qt
    try:
        theme.apply(qapp, "system")
        assert qapp.styleHints().colorScheme() in (Qt.ColorScheme.Light, Qt.ColorScheme.Dark)
        assert theme.P["dark"] == theme.is_dark(qapp.palette())
    finally:
        theme.apply(qapp, "light")


@pytest.mark.parametrize("mode", ["x", "", None, "Dark"])
def test_unknown_mode_is_system(mode):
    from PySide6.QtCore import Qt
    assert theme.color_scheme(mode) == Qt.ColorScheme.Unknown
