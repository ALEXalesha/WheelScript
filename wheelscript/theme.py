"""
Светлая и тёмная тема.

Светлая — родная тема Windows (ttk «vista»). Её цвета рисует сама Windows, поменять их
нельзя, поэтому тёмная собрана на «clam» с перекрашенными элементами. Обычные
tk-виджеты (поля ввода, холсты, меню) стилей ttk не видят — их перекрашивает retint(),
а окна, которые создаёт сам tkinter (simpledialog), берут цвета из базы опций.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import tkinter as tk
from tkinter import ttk

log = logging.getLogger(__name__)

LABELS = {"system": "как в системе", "light": "светлая", "dark": "тёмная"}

LIGHT: dict = {
    "dark": False,
    "bg": "SystemButtonFace", "fg": "SystemButtonText",
    "surface": "#ffffff", "surface2": "#f1f5f9", "border": "#cbd5e1",
    "text": "#334155", "faint": "#7c8799", "tick": "#64748b", "disabled": "#9ca3af",
    "accent": "#2563eb", "accent_active": "#1d4ed8",
    "on": "#16a34a", "off": "#6b7280", "error": "#dc2626",
    "wait_bg": "#fff3c4", "live_bg": "#dbeafe",
    "entry_bg": "#ffffff", "entry_fg": "#000000",
    "menu_bg": "SystemMenu", "menu_fg": "SystemMenuText",
    "select_bg": "SystemHighlight", "select_fg": "SystemHighlightText",
    "button_bg": "SystemButtonFace", "button_active": "SystemButtonFace", "button_pressed": "SystemButtonFace",
}

DARK: dict = {
    "dark": True,
    "bg": "#202124", "fg": "#e5e7eb",
    "surface": "#17181b", "surface2": "#2a2c30", "border": "#3c3f45",
    "text": "#cbd5e1", "faint": "#7d8590", "tick": "#94a3b8", "disabled": "#6b7280",
    "accent": "#3b82f6", "accent_active": "#2563eb",
    "on": "#22c55e", "off": "#9ca3af", "error": "#f87171",
    "wait_bg": "#4a3a0c", "live_bg": "#1e3a5f",
    "entry_bg": "#2a2c30", "entry_fg": "#e5e7eb",
    "menu_bg": "#2a2c30", "menu_fg": "#e5e7eb",
    "select_bg": "#2f5a9e", "select_fg": "#ffffff",
    "button_bg": "#2f3237", "button_active": "#3a3e44", "button_pressed": "#25272b",
}

P: dict = dict(LIGHT)  # текущая палитра: интерфейс берёт цвета отсюда в момент рисования


def system_is_dark() -> bool:
    """Тёмная ли тема приложений в настройках Windows."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except (OSError, ImportError):
        return False


def resolve(mode: str) -> bool:
    if mode == "dark":
        return True
    if mode == "light":
        return False
    return system_is_dark()


def apply(root: tk.Misc, dark: bool) -> None:
    """Палитра + стили ttk + база опций. Виджеты, которые уже есть, перекрашивает retint()."""
    pal = DARK if dark else LIGHT
    P.clear()
    P.update(pal)
    style = ttk.Style(root)
    if dark:
        style.theme_use("clam")
        _configure_dark(style, pal)
    else:
        style.theme_use("vista" if "vista" in style.theme_names() else "default")
    _options(root, pal)


def _configure_dark(s: ttk.Style, p: dict) -> None:
    s.configure(".", background=p["bg"], foreground=p["fg"], bordercolor=p["border"],
                lightcolor=p["bg"], darkcolor=p["bg"], troughcolor=p["surface"],
                fieldbackground=p["entry_bg"], selectbackground=p["select_bg"],
                selectforeground=p["select_fg"], insertcolor=p["fg"], arrowcolor=p["fg"],
                focuscolor=p["accent"])
    s.map(".", foreground=[("disabled", p["disabled"])], background=[("disabled", p["bg"])])
    for name in ("TButton", "TMenubutton"):
        s.configure(name, background=p["button_bg"], lightcolor=p["button_bg"], darkcolor=p["button_bg"],
                    bordercolor=p["border"])
        s.map(name, background=[("pressed", p["button_pressed"]), ("active", p["button_active"])],
              lightcolor=[("active", p["button_active"])], darkcolor=[("active", p["button_active"])])
    s.configure("Accent.TButton", background=p["accent"], foreground="#ffffff",
                lightcolor=p["accent"], darkcolor=p["accent"])
    s.map("Accent.TButton", background=[("pressed", p["accent_active"]), ("active", p["accent_active"])],
          lightcolor=[("active", p["accent_active"])], darkcolor=[("active", p["accent_active"])])
    field = dict(fieldbackground=p["entry_bg"], foreground=p["entry_fg"], background=p["button_bg"],
                 bordercolor=p["border"], lightcolor=p["entry_bg"], darkcolor=p["entry_bg"],
                 arrowcolor=p["fg"], insertcolor=p["entry_fg"])
    for name in ("TEntry", "TCombobox", "TSpinbox"):
        s.configure(name, **field)
        s.map(name, fieldbackground=[("readonly", p["entry_bg"]), ("disabled", p["bg"])],
              foreground=[("readonly", p["entry_fg"])], bordercolor=[("focus", p["accent"])],
              selectbackground=[("readonly", p["entry_bg"])], selectforeground=[("readonly", p["entry_fg"])])
    for name in ("TCheckbutton", "TRadiobutton"):
        s.configure(name, background=p["bg"], foreground=p["fg"], indicatorbackground=p["entry_bg"],
                    indicatorforeground=p["fg"], upperbordercolor=p["border"], lowerbordercolor=p["border"])
        s.map(name, background=[("active", p["bg"])],
              indicatorbackground=[("pressed", p["button_pressed"]), ("active", p["button_active"])])
    s.configure("Treeview", background=p["surface"], fieldbackground=p["surface"], foreground=p["fg"],
                bordercolor=p["border"], lightcolor=p["surface"], darkcolor=p["surface"])
    s.map("Treeview", background=[("selected", p["select_bg"])], foreground=[("selected", p["select_fg"])])
    s.configure("Treeview.Heading", background=p["surface2"], foreground=p["fg"], bordercolor=p["border"],
                lightcolor=p["surface2"], darkcolor=p["surface2"], relief="flat")
    s.map("Treeview.Heading", background=[("active", p["button_active"])])
    s.configure("TScrollbar", background=p["button_bg"], troughcolor=p["surface"], bordercolor=p["border"],
                lightcolor=p["button_bg"], darkcolor=p["button_bg"], arrowcolor=p["fg"], gripcount=0)
    s.map("TScrollbar", background=[("active", p["button_active"])])
    s.configure("TScale", background=p["button_bg"], troughcolor=p["surface2"], bordercolor=p["border"],
                lightcolor=p["button_bg"], darkcolor=p["button_bg"])
    s.map("TScale", background=[("active", p["button_active"])])
    s.configure("TLabelframe", background=p["bg"], bordercolor=p["border"])
    s.configure("TLabelframe.Label", background=p["bg"], foreground=p["fg"])
    s.configure("TPanedwindow", background=p["bg"])
    s.configure("Sash", background=p["bg"], lightcolor=p["border"], bordercolor=p["border"])


def _options(root: tk.Misc, p: dict) -> None:
    for pattern, value in (
            ("*Toplevel.background", p["bg"]), ("*Frame.background", p["bg"]),
            ("*Label.background", p["bg"]), ("*Label.foreground", p["fg"]),
            ("*Button.background", p["button_bg"]), ("*Button.foreground", p["fg"]),
            ("*Button.activeBackground", p["button_active"]), ("*Button.activeForeground", p["fg"]),
            ("*Entry.background", p["entry_bg"]), ("*Entry.foreground", p["entry_fg"]),
            ("*Entry.insertBackground", p["entry_fg"]),
            ("*Entry.selectBackground", p["select_bg"]), ("*Entry.selectForeground", p["select_fg"]),
            ("*Menu.background", p["menu_bg"]), ("*Menu.foreground", p["menu_fg"]),
            ("*Menu.activeBackground", p["select_bg"]), ("*Menu.activeForeground", p["select_fg"]),
            ("*TCombobox*Listbox.background", p["entry_bg"]), ("*TCombobox*Listbox.foreground", p["entry_fg"]),
            ("*TCombobox*Listbox.selectBackground", p["select_bg"]),
            ("*TCombobox*Listbox.selectForeground", p["select_fg"])):
        root.option_add(pattern, value)


def retint(w: tk.Misc) -> None:
    """Перекрасить уже созданные tk-виджеты в текущую палитру P (рекурсивно)."""
    p = P
    cls = w.winfo_class()
    try:
        if cls in ("Tk", "Toplevel"):
            w.configure(background=p["bg"])
        elif cls == "Entry":
            w.configure(background=p["entry_bg"], readonlybackground=p["entry_bg"], foreground=p["entry_fg"],
                        insertbackground=p["entry_fg"], highlightbackground=p["border"],
                        highlightcolor=p["accent"])
        elif cls == "Canvas":
            w.configure(background=p["surface"], highlightbackground=p["border"])
        elif cls == "Menu":
            w.configure(background=p["menu_bg"], foreground=p["menu_fg"],
                        activebackground=p["select_bg"], activeforeground=p["select_fg"])
        elif cls == "TCombobox":
            # выпадающий список — отдельное окно, которого нет среди детей tkinter
            pd = w.tk.call("ttk::combobox::PopdownWindow", w)
            w.tk.call(f"{pd}.f.l", "configure", "-background", p["entry_bg"], "-foreground", p["entry_fg"],
                      "-selectbackground", p["select_bg"], "-selectforeground", p["select_fg"])
    except tk.TclError:
        log.debug("retint %s failed", w, exc_info=True)
    for child in w.winfo_children():
        retint(child)


def set_titlebar(win: tk.Misc, dark: bool) -> None:
    """Тёмный заголовок окна (Windows 10 20H1+ / 11). На старых системах просто ничего не делает."""
    if sys.platform != "win32":
        return
    try:
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        value = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE: 20, в ранних сборках Windows 10 — 19
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value),
                                                         ctypes.sizeof(value)) == 0:
                break
        # перерисовать рамку сейчас, а не при следующей активации окна
        # (SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x37)
    except Exception:  # noqa: BLE001
        log.debug("titlebar theme failed", exc_info=True)
