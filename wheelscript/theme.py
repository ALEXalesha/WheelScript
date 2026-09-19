"""
Светлая и тёмная тема.

Окна, кнопки, списки, меню и заголовок окна красит сам Qt (стиль windows11 и
QStyleHints.setColorScheme). Здесь только смысловые цвета того, что программа рисует
сама: монитор руля, полоска проверки, точка статуса, подсветка срабатывающих привязок.
"""

from __future__ import annotations

LABELS = {"system": "как в системе", "light": "светлая", "dark": "тёмная"}

LIGHT: dict = {
    "dark": False,
    "bg": "#f3f3f3", "fg": "#1b1b1b",
    "surface": "#ffffff", "surface2": "#eef2f6", "border": "#c4ccd6",
    "text": "#334155", "faint": "#6b7686", "tick": "#64748b", "disabled": "#8a919c",
    "accent": "#2563eb",
    "on": "#15803d", "off": "#5f6672", "error": "#c81e1e",
    "wait_bg": "#fff3c4", "live_bg": "#dbeafe", "entry_fg": "#000000",
}

DARK: dict = {
    "dark": True,
    "bg": "#202020", "fg": "#e5e7eb",
    "surface": "#17181b", "surface2": "#2a2c30", "border": "#3c3f45",
    "text": "#cbd5e1", "faint": "#8a929c", "tick": "#94a3b8", "disabled": "#6b7280",
    "accent": "#3b82f6",
    "on": "#22c55e", "off": "#9ca3af", "error": "#f87171",
    "wait_bg": "#4a3a0c", "live_bg": "#1e3a5f", "entry_fg": "#e5e7eb",
}

P: dict = dict(LIGHT)  # текущая палитра: интерфейс берёт цвета отсюда в момент рисования


def color_scheme(mode: str):
    from PySide6.QtCore import Qt
    return {"light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}.get(mode, Qt.ColorScheme.Unknown)


def is_dark(palette) -> bool:
    return palette.window().color().lightness() < 128


def sync(app) -> bool:
    """Выбрать палитру P по тому, какую тему Qt показывает сейчас. True — тёмная."""
    dark = is_dark(app.palette())
    P.clear()
    P.update(DARK if dark else LIGHT)
    return dark


def apply(app, mode: str) -> bool:
    """Режим «system» / «light» / «dark»: Qt меняет палитру, мы — смысловые цвета."""
    app.styleHints().setColorScheme(color_scheme(mode))
    app.processEvents()
    return sync(app)
