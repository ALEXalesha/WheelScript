"""Палитры тем: полнота, контраст текста, выбор «как в системе» (без окон)."""

import re

import pytest

from wheelscript import theme
from wheelscript.model import THEMES

HEX = re.compile(r"^#[0-9a-f]{6}$")

# (цвет текста, цвет фона, минимальный контраст по WCAG)
PAIRS = [
    ("fg", "bg", 7.0), ("entry_fg", "entry_bg", 7.0), ("text", "surface", 7.0), ("text", "surface2", 4.5),
    ("off", "bg", 4.5), ("select_fg", "select_bg", 4.5), ("entry_fg", "wait_bg", 4.5),
    ("fg", "live_bg", 4.5), ("on", "bg", 3.0), ("error", "bg", 3.0), ("faint", "surface", 3.0),
    ("faint", "surface2", 3.0),  # «ещё не двигалась» рисуется поверх полоски оси
    ("fg", "button_bg", 4.5),
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


def test_dark_palette_is_all_hex():
    for k, v in theme.DARK.items():
        if k != "dark":
            assert HEX.match(v), f"{k}={v!r}"


@pytest.mark.parametrize("pal", [theme.LIGHT, theme.DARK], ids=["light", "dark"])
@pytest.mark.parametrize("fg,bg,minimum", PAIRS)
def test_text_is_readable(pal, fg, bg, minimum):
    if not (HEX.match(pal[fg]) and HEX.match(pal[bg])):
        pytest.skip("системный цвет Windows")
    assert contrast(pal[fg], pal[bg]) >= minimum, f"{fg} на {bg}: {contrast(pal[fg], pal[bg]):.2f}"


def test_labels_cover_all_modes():
    assert set(theme.LABELS) == set(THEMES)


def test_resolve(monkeypatch):
    monkeypatch.setattr(theme, "system_is_dark", lambda: True)
    assert theme.resolve("dark") and theme.resolve("system") and not theme.resolve("light")
    monkeypatch.setattr(theme, "system_is_dark", lambda: False)
    assert not theme.resolve("system") and theme.resolve("dark")


def test_system_is_dark_is_bool():
    assert isinstance(theme.system_is_dark(), bool)
