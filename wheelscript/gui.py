"""Интерфейс на tkinter."""

from __future__ import annotations

import logging
import os
import queue
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable, Optional

from . import APP_NAME, __version__, keys, labels, storage, theme
from .capture import Capture, adapt_source
from .engine import binding_value, shape
from .model import (ANALOG_ACTIONS, DEFAULT_MOVE_SPEED, DEFAULT_WHEEL_SPEED, MOVE_SPEED, RUMBLE, TICK_RATE,
                    WHEEL_SPEED, Binding, Config, InputSource, Profile, Settings, clean_text,
                    default_profile, gamepad_profile, unique_name)
from .presets import PRESETS
from .theme import P

log = logging.getLogger(__name__)

POLL_MS = 40
CAPTURE_TIMEOUT = 15.0
THEME_CHECK_POLLS = 50  # «как в системе»: сверяться с Windows раз в ~2 с
LABEL_W = 20


def _float(var: tk.Variable, default: float) -> float:
    try:
        return float(var.get())
    except (tk.TclError, ValueError):
        return default


def _entry_style() -> dict:
    return dict(readonlybackground=P["entry_bg"], foreground=P["entry_fg"], relief="flat", bd=0,
                highlightthickness=1, highlightbackground=P["border"], highlightcolor=P["accent"])


class Choice(ttk.Combobox):
    """Выпадающий список: показывает подписи, хранит ключи."""

    def __init__(self, master, mapping: dict[str, str], value: str,
                 command: Optional[Callable[[str], None]] = None, width: int = 34):
        self._keys = list(mapping)
        super().__init__(master, values=[mapping[k] for k in self._keys], state="readonly", width=width)
        self.set_key(value)
        if command:
            self.bind("<<ComboboxSelected>>", lambda _e: command(self.get_key()))

    def get_key(self) -> str:
        i = self.current()
        return self._keys[i] if 0 <= i < len(self._keys) else self._keys[0]

    def set_key(self, key: str) -> None:
        self.current(self._keys.index(key) if key in self._keys else 0)


class InputField(ttk.Frame):
    """Поле «ввод с руля»: клик — и первая нажатая кнопка/ось/крестовина попадает в поле."""

    def __init__(self, master, service, source: InputSource, on_change: Callable[[InputSource], None]):
        super().__init__(master)
        self.service = service
        self.source = source
        self.on_change = on_change
        self.var = tk.StringVar()
        self.entry = tk.Entry(self, textvariable=self.var, state="readonly", cursor="hand2", width=44,
                              **_entry_style())
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.entry.bind("<Button-1>", self._click)
        self.entry.bind("<Escape>", self._escape)
        ttk.Button(self, text="Сбросить", command=self.clear).pack(side="left", padx=(6, 0))
        self._capture: Optional[Capture] = None
        self._job: Optional[str] = None
        self._deadline = 0.0
        self.refresh()

    @property
    def capturing(self) -> bool:
        return self._capture is not None

    def refresh(self) -> None:
        if self._capture:
            return
        if self.source.is_set:
            self.var.set(labels.source_text(self.source, self.service.device_names()))
        else:
            self.var.set("кликни сюда и нажми кнопку / сдвинь ось на руле")

    def _click(self, _e=None):
        self.start()
        return "break"

    def _escape(self, _e=None):
        if self._capture:
            self.cancel()
            return "break"
        return None

    def start(self) -> None:
        if self._capture:
            return
        states, infos = self.service.snapshot()
        if not infos:
            messagebox.showwarning(APP_NAME, "Руль не подключён — нечего считывать.",
                                   parent=self.winfo_toplevel())
            return
        self._capture = Capture(states)
        self._deadline = time.monotonic() + CAPTURE_TIMEOUT
        self.entry.configure(readonlybackground=P["wait_bg"])
        self.var.set("жду: нажми кнопку, сдвинь ось или крестовину…  (Esc — отмена)")
        self.entry.focus_set()
        self._poll()

    def _poll(self) -> None:
        self._job = None
        if not self._capture:
            return
        states, _ = self.service.snapshot()
        found = self._capture.feed(states)
        if found is not None:
            self._stop()
            self.source = found
            self.on_change(found)
            self.refresh()
            return
        if time.monotonic() > self._deadline:
            self.cancel()
            return
        self._job = self.after(15, self._poll)

    def _stop(self) -> None:
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        self._capture = None
        self.entry.configure(readonlybackground=P["entry_bg"])

    def cancel(self) -> None:
        self._stop()
        self.refresh()

    def clear(self) -> None:
        self._stop()
        self.source = InputSource()
        self.on_change(self.source)
        self.refresh()

    def set_source(self, src: InputSource) -> None:
        self.source = src
        self.refresh()

    def destroy(self) -> None:
        self._stop()
        super().destroy()


class KeyField(ttk.Frame):
    """Поле клавиши: клик — нажми клавишу/сочетание на клавиатуре. Плюс ручной выбор из списка."""

    def __init__(self, master, value: tuple[str, ...], on_change: Callable[[tuple[str, ...]], None],
                 combo: bool = True, allow_empty: bool = False,
                 on_capture: Optional[Callable[[bool], None]] = None, width: int = 24):
        super().__init__(master)
        self.value = tuple(value)
        self.on_change = on_change
        self.combo = combo
        self.allow_empty = allow_empty
        self.on_capture = on_capture
        self.var = tk.StringVar()
        self.entry = tk.Entry(self, textvariable=self.var, state="readonly", cursor="hand2", width=width,
                              **_entry_style())
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.entry.bind("<Button-1>", self._click)
        self.entry.bind("<KeyPress>", self._press)
        self.entry.bind("<KeyRelease>", self._release)
        self.entry.bind("<FocusOut>", lambda _e: self._finish())
        self._names = list(keys.KEY_NAMES)
        self.pick = ttk.Combobox(self, state="readonly", width=12,
                                 values=["выбрать…"] + [keys.display(n) for n in self._names])
        self.pick.current(0)
        self.pick.bind("<<ComboboxSelected>>", self._picked)
        self.pick.pack(side="left", padx=(6, 0))
        if allow_empty:
            ttk.Button(self, text="✕", width=3, command=lambda: self._set(())).pack(side="left", padx=(4, 0))
        self._capturing = False
        self._down: set[str] = set()
        self._collected: list[str] = []
        self._job: Optional[str] = None
        self.refresh()

    def refresh(self) -> None:
        if not self._capturing:
            self.var.set(keys.combo_text(self.value) if self.value else "нет")

    def _click(self, _e=None):
        if self._capturing:
            return "break"
        self._capturing = True
        self._down.clear()
        self._collected.clear()
        if self.on_capture:
            self.on_capture(True)
        self.entry.configure(readonlybackground=P["wait_bg"])
        self.var.set("нажми клавишу" + (" или сочетание" if self.combo else "") + "…  (Esc — отмена)")
        self.entry.focus_set()
        self._job = self.after(int(CAPTURE_TIMEOUT * 1000), self._finish)
        return "break"

    def _press(self, e):
        if not self._capturing:
            return None
        name = keys.from_tk(e.keycode, e.keysym)
        if name == "esc" and not self._down and not self._collected:
            self._finish(cancel=True)
            return "break"
        if name:
            self._down.add(name)
            if name not in self._collected:
                self._collected.append(name)
        return "break"

    def _release(self, e):
        if not self._capturing:
            return None
        name = keys.from_tk(e.keycode, e.keysym)
        if name and name not in self._collected:  # PrintScreen приходит только отпусканием
            self._collected.append(name)
        self._down.discard(name)
        if not self._down and self._collected:
            self._finish()
        return "break"

    def _finish(self, cancel: bool = False) -> None:
        if not self._capturing:
            return
        self._capturing = False
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        self.entry.configure(readonlybackground=P["entry_bg"])
        if self.on_capture:
            self.on_capture(False)
        combo = keys.normalize_combo(self._collected)
        if not cancel and combo:
            self._set(combo if self.combo else combo[-1:])
        self.refresh()

    def _picked(self, _e=None) -> None:
        i = self.pick.current()
        self.pick.current(0)
        if i > 0:
            self._set((self._names[i - 1],))

    def _set(self, value: tuple[str, ...]) -> None:
        if not value and not self.allow_empty:
            return
        self.value = value
        self.on_change(value)
        self.refresh()

    def destroy(self) -> None:
        self._finish(cancel=True)
        super().destroy()


class Monitor(ttk.LabelFrame):
    """Живой вид всех осей, кнопок и крестовин выбранного устройства."""

    def __init__(self, master, selected: str, on_select: Callable[[str], None]):
        super().__init__(master, text="Что сейчас нажато на руле", padding=8)
        self.on_select = on_select
        self._selected = selected
        self._devices: list[str] = []
        self.device = ttk.Combobox(self, state="readonly")
        self.device.pack(fill="x")
        self.device.bind("<<ComboboxSelected>>", self._changed)
        self.canvas = tk.Canvas(self, width=320, height=430, bg=P["surface"], highlightthickness=1,
                                highlightbackground=P["border"])
        self.canvas.pack(fill="both", expand=True, pady=(8, 0))
        self._last = None

    def _changed(self, _e=None) -> None:
        i = self.device.current()
        if 0 <= i < len(self._devices):
            self._selected = self._devices[i]
            self.on_select(self._selected)

    def current_key(self) -> Optional[str]:
        return self._selected if self._selected in self._devices else (self._devices[0] if self._devices else None)

    def update_view(self, states, infos) -> None:
        keys_ = [d.key for d in infos]
        if keys_ != self._devices:
            self._devices = keys_
            self.device["values"] = [d.name for d in infos] or ["(руль не найден)"]
            key = self.current_key()
            self.device.current(keys_.index(key) if key in keys_ else 0)
        key = self.current_key()
        st = states.get(key) if key else None
        sig = (key, st, self.canvas.winfo_width())
        if sig == self._last:
            return
        self._last = sig
        self._draw(st)

    def _draw(self, st) -> None:
        c = self.canvas
        c.delete("all")
        w = max(c.winfo_width(), 200)
        if st is None:
            c.create_text(w / 2, 60, text="Руль не найден.\nПодключи его — список обновится сам.",
                          justify="center", fill=P["off"])
            return
        y = 8
        x0, x1 = 58, w - 58
        mid = (x0 + x1) / 2
        for i, v in enumerate(st.axes):
            c.create_text(8, y + 8, text=f"Ось {i}", anchor="w", fill=P["text"])
            c.create_rectangle(x0, y + 2, x1, y + 14, outline=P["border"], fill=P["surface2"])
            if v is None:
                c.create_text(mid, y + 8, text="ещё не двигалась", fill=P["faint"], font=("Segoe UI", 7))
            else:
                xv = mid + v * (x1 - x0) / 2
                c.create_rectangle(min(mid, xv), y + 2, max(mid, xv), y + 14, fill=P["accent"], outline="")
                c.create_line(mid, y, mid, y + 16, fill=P["faint"])
                c.create_text(w - 8, y + 8, text=f"{v:+.2f}", anchor="e", fill=P["text"])
            y += 20
        y += 6
        c.create_text(8, y, text="Кнопки", anchor="nw", fill=P["text"])
        y += 18
        cols = max(1, int((w - 16) // 34))
        for i, pressed in enumerate(st.buttons):
            r, col = divmod(i, cols)
            x, yy = 8 + col * 34, y + r * 26
            c.create_rectangle(x, yy, x + 30, yy + 22, fill=P["accent"] if pressed else P["surface2"], outline=P["border"])
            c.create_text(x + 15, yy + 11, text=str(i), fill="#ffffff" if pressed else P["text"])
        y += ((len(st.buttons) + cols - 1) // cols) * 26 + 8
        for i, (hx, hy) in enumerate(st.hats):
            arrow = {(0, 1): "↑", (0, -1): "↓", (-1, 0): "←", (1, 0): "→",
                     (1, 1): "↗", (-1, 1): "↖", (1, -1): "↘", (-1, -1): "↙"}.get((hx, hy), "·")
            c.create_text(8, y, text=f"Крестовина {i}:  {arrow}", anchor="nw", fill=P["text"])
            y += 20


class BindingDialog(tk.Toplevel):
    """Редактор одной привязки. Пока открыт, маппинг на паузе, чтобы руль не «кликал» по окну."""

    KINDS = ("key", "mouse_button", "mouse_move", "mouse_wheel", "pad_button", "pad_stick", "pad_trigger", "toggle")

    def __init__(self, app: "App", binding: Binding, title: str):
        super().__init__(app.root)
        self.app = app
        self.service = app.service
        self.result: Optional[Binding] = None
        self.title(title)
        self.transient(app.root)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.service.suspend()
        self._closed = False

        a = binding.action
        self.keys_val = a.keys or ("w",)
        self.press_val = a.press
        self.button_val = a.button
        self.move_dir = a.direction if a.kind == "mouse_move" else "right"
        self.wheel_dir = a.direction if a.kind == "mouse_wheel" else "up"
        self.pad_button_val = a.pad if a.kind == "pad_button" else "a"
        self.stick_val = a.pad if a.kind == "pad_stick" else "left"
        self.stick_dir = a.direction if a.kind == "pad_stick" else "right"
        self.trigger_val = a.pad if a.kind == "pad_trigger" else "rt"
        self.move_speed = tk.DoubleVar(value=a.speed if a.kind == "mouse_move" else DEFAULT_MOVE_SPEED)
        self.wheel_speed = tk.DoubleVar(value=a.speed if a.kind == "mouse_wheel" else DEFAULT_WHEEL_SPEED)
        self.threshold = tk.DoubleVar(value=binding.threshold)
        self.deadzone = tk.DoubleVar(value=binding.deadzone)
        self.curve = tk.DoubleVar(value=binding.curve)
        self.invert = tk.BooleanVar(value=binding.invert)
        self.enabled = tk.BooleanVar(value=binding.enabled)
        self.name_var = tk.StringVar(value=binding.name)

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="Название", width=LABEL_W).grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(body, textvariable=self.name_var, width=46).grid(row=0, column=1, sticky="we", pady=4)

        ttk.Label(body, text="Ввод с руля", width=LABEL_W).grid(row=1, column=0, sticky="w", pady=4)
        self.input = InputField(body, self.service, binding.source, self._on_source)
        self.input.grid(row=1, column=1, sticky="we", pady=4)

        self.mode_label = ttk.Label(body, text="", width=LABEL_W)
        self.mode_label.grid(row=2, column=0, sticky="w", pady=4)
        self.axis_mode = Choice(body, labels.AXIS_MODE_LABELS,
                                binding.source.mode if binding.source.kind == "axis" else "full")
        self.hat_mode = Choice(body, labels.HAT_DIR_LABELS,
                               binding.source.mode if binding.source.kind == "hat" else "up")

        ttk.Label(body, text="Действие", width=LABEL_W).grid(row=3, column=0, sticky="w", pady=4)
        self.kind = Choice(body, {k: labels.ACTION_LABELS[k] for k in self.KINDS},
                           a.kind if a.kind in self.KINDS else "key", command=self._on_kind)
        self.kind.grid(row=3, column=1, sticky="w", pady=4)

        self.params = ttk.Frame(body)
        self.params.grid(row=4, column=0, columnspan=2, sticky="we")
        self.params.columnconfigure(1, weight=1)

        self.tune = ttk.LabelFrame(body, text="Тонкая настройка", padding=8)
        self.tune.grid(row=5, column=0, columnspan=2, sticky="we", pady=(8, 0))
        self.tune.columnconfigure(1, weight=1)

        pv = ttk.LabelFrame(body, text="Проверка — покрути / нажми на руле", padding=8)
        pv.grid(row=6, column=0, columnspan=2, sticky="we", pady=(8, 0))
        self.preview = tk.Canvas(pv, height=26, bg=P["surface"], highlightthickness=0)
        self.preview.pack(fill="x")
        self.preview_text = ttk.Label(pv, text="")
        self.preview_text.pack(anchor="w", pady=(4, 0))

        btns = ttk.Frame(body)
        btns.grid(row=7, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="Отмена", command=self._cancel).pack(side="right")
        ttk.Button(btns, text="Сохранить", command=self._ok, style="Accent.TButton").pack(side="right", padx=(0, 8))

        self.bind("<Escape>", lambda _e: self._cancel())
        self._build_params()
        self._update_mode_row()
        self._build_tune()

        self.update_idletasks()
        px = app.root.winfo_rootx() + (app.root.winfo_width() - self.winfo_width()) // 2
        py = app.root.winfo_rooty() + (app.root.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(px, 0)}+{max(py, 0)}")
        theme.retint(self)
        theme.set_titlebar(self, P["dark"])
        self.grab_set()
        self.focus_set()
        self._job = self.after(POLL_MS, self._tick)
        self.wait_window()

    # --- построение ---

    def _row(self, parent, r: int, text: str, widget) -> None:
        ttk.Label(parent, text=text, width=LABEL_W).grid(row=r, column=0, sticky="w", pady=4)
        widget.grid(row=r, column=1, sticky="w", pady=4)

    def _build_params(self) -> None:
        for w in self.params.winfo_children():
            w.destroy()
        k = self.kind.get_key()
        f = self.params
        if k == "key":
            self._row(f, 0, "Клавиша", KeyField(f, self.keys_val, self._set_keys))
            self._row(f, 1, "Режим нажатия", Choice(f, labels.PRESS_LABELS, self.press_val, self._set_press))
        elif k == "mouse_button":
            self._row(f, 0, "Кнопка мыши", Choice(f, labels.MOUSE_BUTTON_LABELS, self.button_val, self._set_button))
            self._row(f, 1, "Режим нажатия", Choice(f, labels.PRESS_LABELS, self.press_val, self._set_press))
        elif k == "mouse_move":
            self._row(f, 0, "Направление", Choice(f, labels.DIRECTION_LABELS, self.move_dir, self._set_move_dir))
            row = ttk.Frame(f)
            ttk.Spinbox(row, from_=MOVE_SPEED[0], to=MOVE_SPEED[1], increment=50, width=8,
                        textvariable=self.move_speed).pack(side="left")
            ttk.Label(row, text=" пикселей в секунду при полном отклонении").pack(side="left")
            self._row(f, 1, "Скорость", row)
        elif k == "mouse_wheel":
            self._row(f, 0, "Направление", Choice(f, labels.DIRECTION_LABELS, self.wheel_dir, self._set_wheel_dir))
            row = ttk.Frame(f)
            ttk.Spinbox(row, from_=1, to=WHEEL_SPEED[1], increment=1, width=8,
                        textvariable=self.wheel_speed).pack(side="left")
            ttk.Label(row, text=" щелчков колеса в секунду").pack(side="left")
            self._row(f, 1, "Скорость", row)
        elif k in ("pad_button", "pad_stick", "pad_trigger"):
            if k == "pad_button":
                self._row(f, 0, "Кнопка геймпада",
                          Choice(f, labels.PAD_BUTTON_LABELS, self.pad_button_val, self._set_pad_button))
                self._row(f, 1, "Режим нажатия", Choice(f, labels.PRESS_LABELS, self.press_val, self._set_press))
            elif k == "pad_stick":
                self._row(f, 0, "Стик", Choice(f, labels.PAD_STICK_LABELS, self.stick_val, self._set_stick))
                self._row(f, 1, "Направление",
                          Choice(f, labels.DIRECTION_LABELS, self.stick_dir, self._set_stick_dir))
            else:
                self._row(f, 0, "Курок", Choice(f, labels.PAD_TRIGGER_LABELS, self.trigger_val, self._set_trigger))
            ttk.Label(f, text="Игра увидит виртуальный геймпад Xbox 360 (нужен драйвер ViGEmBus).",
                      foreground=P["off"]).grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 4))
        else:
            ttk.Label(f, text="Нажатие включает или выключает весь маппинг — то же, что горячая клавиша.",
                      foreground=P["off"]).grid(row=0, column=0, columnspan=2, sticky="w", pady=4)

    def _scale(self, parent, r: int, text: str, var: tk.DoubleVar, lo: float, hi: float, fmt) -> None:
        ttk.Label(parent, text=text, width=LABEL_W).grid(row=r, column=0, sticky="w", pady=2)
        value = ttk.Label(parent, width=6)
        ttk.Scale(parent, from_=lo, to=hi, variable=var, length=260,
                  command=lambda _v: value.configure(text=fmt(_float(var, lo)))).grid(row=r, column=1, sticky="we")
        value.grid(row=r, column=2, sticky="e", padx=(8, 0))
        value.configure(text=fmt(_float(var, lo)))

    def _build_tune(self) -> None:
        for w in self.tune.winfo_children():
            w.destroy()
        t = self.tune
        r = 0
        pct = lambda v: f"{v:.0%}"  # noqa: E731
        is_axis = self.input.source.kind == "axis"
        if self.kind.get_key() in ANALOG_ACTIONS and is_axis:
            self._scale(t, r, "Мёртвая зона", self.deadzone, 0.0, 0.5, pct)
            r += 1
            self._scale(t, r, "Кривая (1 = линейно)", self.curve, 0.2, 3.0, lambda v: f"{v:.2f}")
            r += 1
        elif is_axis and self.kind.get_key() not in ANALOG_ACTIONS:
            self._scale(t, r, "Порог срабатывания", self.threshold, 0.01, 0.99, pct)
            r += 1
        ttk.Checkbutton(t, text="Инвертировать", variable=self.invert).grid(row=r, column=0, sticky="w", pady=(4, 0))
        ttk.Checkbutton(t, text="Привязка включена", variable=self.enabled).grid(row=r, column=1, sticky="w",
                                                                                  pady=(4, 0))

    def _update_mode_row(self) -> None:
        self.axis_mode.grid_remove()
        self.hat_mode.grid_remove()
        kind = self.input.source.kind
        if kind == "axis":
            self.axis_mode.set_key(self.input.source.mode)
            self.mode_label.configure(text="Как читать ось")
            self.axis_mode.grid(row=2, column=1, sticky="w", pady=4)
        elif kind == "hat":
            self.hat_mode.set_key(self.input.source.mode)
            self.mode_label.configure(text="Направление")
            self.hat_mode.grid(row=2, column=1, sticky="w", pady=4)
        else:
            self.mode_label.configure(text="")

    # --- реакции ---

    def _on_source(self, src: InputSource) -> None:
        src = adapt_source(src, self.kind.get_key())
        self.input.set_source(src)
        self._update_mode_row()
        self._build_tune()

    def _on_kind(self, kind: str) -> None:
        src = self._current_source()
        adapted = adapt_source(src, kind)
        if adapted != src:
            self.input.set_source(adapted)
            self._update_mode_row()
        self._build_params()
        self._build_tune()

    def _set_keys(self, v): self.keys_val = v
    def _set_press(self, v): self.press_val = v
    def _set_button(self, v): self.button_val = v
    def _set_move_dir(self, v): self.move_dir = v
    def _set_wheel_dir(self, v): self.wheel_dir = v
    def _set_pad_button(self, v): self.pad_button_val = v
    def _set_stick(self, v): self.stick_val = v
    def _set_stick_dir(self, v): self.stick_dir = v
    def _set_trigger(self, v): self.trigger_val = v

    def _current_source(self) -> InputSource:
        src = self.input.source
        if src.kind == "axis":
            return InputSource.axis(src.index, self.axis_mode.get_key(), src.device)
        if src.kind == "hat":
            return InputSource.hat(src.index, self.hat_mode.get_key(), src.device)
        return src

    def build(self) -> Binding:
        k = self.kind.get_key()
        if k == "mouse_move":
            direction, speed = self.move_dir, _float(self.move_speed, DEFAULT_MOVE_SPEED)
        elif k == "mouse_wheel":
            direction, speed = self.wheel_dir, _float(self.wheel_speed, DEFAULT_WHEEL_SPEED)
        elif k == "pad_stick":
            direction, speed = self.stick_dir, DEFAULT_MOVE_SPEED
        else:
            direction, speed = "right", DEFAULT_MOVE_SPEED
        pad = {"pad_button": self.pad_button_val, "pad_stick": self.stick_val,
               "pad_trigger": self.trigger_val}.get(k, "")
        return Binding.from_dict({
            "name": self.name_var.get(),
            "source": self._current_source().to_dict(),
            "action": {"kind": k, "keys": list(self.keys_val), "button": self.button_val,
                       "direction": direction, "speed": speed, "press": self.press_val, "pad": pad},
            "enabled": bool(self.enabled.get()),
            "threshold": _float(self.threshold, 0.5),
            "deadzone": _float(self.deadzone, 0.05),
            "curve": _float(self.curve, 1.0),
            "invert": bool(self.invert.get()),
        })

    def _tick(self) -> None:
        self._job = None
        if self._closed:
            return
        try:
            states, infos = self.service.snapshot()
            b = self.build()
            v = binding_value(b, states, infos[0].key if infos else None)
            self._draw_preview(b, v)
        except Exception:  # noqa: BLE001
            log.exception("preview failed")
        self._job = self.after(POLL_MS, self._tick)

    def _draw_preview(self, b: Binding, v: Optional[float]) -> None:
        c = self.preview
        c.delete("all")
        w = max(c.winfo_width(), 200)
        c.create_rectangle(1, 4, w - 1, 22, outline=P["border"], fill=P["surface2"])
        if v is None:
            self.preview_text.configure(text="нет данных: ввод не назначен или ось ещё не двигалась",
                                        foreground=P["off"])
            return
        signed = b.source.kind == "axis" and b.source.mode == "full"
        if b.action.is_analog:
            m = shape(abs(v), b.deadzone, b.curve) * (1 if v >= 0 else -1)
            if signed:
                mid = w / 2
                c.create_rectangle(min(mid, mid + m * mid), 4, max(mid, mid + m * mid), 22, fill=P["accent"], outline="")
                c.create_line(mid, 2, mid, 24, fill=P["tick"])
            else:
                c.create_rectangle(1, 4, 1 + abs(m) * (w - 2), 22, fill=P["accent"], outline="")
            self.preview_text.configure(text=f"значение {v:+.2f} → сила {abs(m):.0%}",
                                        foreground=P["on"] if m else P["off"])
        else:
            mag = abs(v)
            active = mag >= b.threshold
            c.create_rectangle(1, 4, 1 + mag * (w - 2), 22, fill=P["on"] if active else P["accent"], outline="")
            if b.source.kind == "axis":
                tx = 1 + b.threshold * (w - 2)
                c.create_line(tx, 0, tx, 26, fill=P["error"], width=2)
            self.preview_text.configure(text=("СРАБОТАЛО" if active else "не нажато") + f"  ({mag:.0%})",
                                        foreground=P["on"] if active else P["off"])

    def _ok(self) -> None:
        b = self.build()
        if b.action.kind == "key" and not b.action.keys:
            messagebox.showerror(APP_NAME, "Выбери клавишу.", parent=self)
            return
        if not b.source.is_set and not messagebox.askyesno(
                APP_NAME, "Ввод с руля не назначен — привязка не будет срабатывать. Сохранить так?", parent=self):
            return
        self.result = b
        self._close()

    def _cancel(self) -> None:
        if self.input.capturing:
            self.input.cancel()
            return
        self._close()

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._job:
            self.after_cancel(self._job)
        self.service.resume()
        self.grab_release()
        self.destroy()


class App:
    def __init__(self, root: tk.Tk, service, cfg: Config, cfg_path: Path, warning: Optional[str] = None):
        self.root = root
        self.service = service
        self.cfg = cfg
        self.cfg_path = cfg_path
        self._live: dict[str, bool] = {}
        self._error: Optional[str] = None
        self._infos: list = []
        self._closing = False

        title = f"{APP_NAME} {__version__}" + ("  (portable)" if storage.is_portable() else "")
        root.title(title)
        root.minsize(980, 600)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._dark = False
        self._theme_polls = 0
        self._apply_theme()
        self._build()
        self._retint()
        self._refresh_profiles()
        self._refresh_tree()

        service.set_toggle_key(cfg.settings.toggle_key)
        service.set_tick_rate(cfg.settings.tick_rate)
        service.set_rumble(cfg.settings.rumble / 100)
        service.set_profile(cfg.active)
        if cfg.settings.start_enabled:
            service.set_enabled(True)
        self._update_status()
        root.after(POLL_MS, self._poll)
        if warning:
            root.after(300, lambda: messagebox.showwarning(APP_NAME, warning, parent=root))

    # --- оформление ---

    def _apply_theme(self) -> None:
        self._dark = theme.resolve(self.cfg.settings.theme)
        theme.apply(self.root, self._dark)
        # стили ttk живут внутри темы: после смены темы их нужно задать заново
        style = ttk.Style(self.root)
        scale = self.root.winfo_fpixels("1i") / 96.0
        style.configure("Treeview", rowheight=int(24 * scale))
        style.configure("Status.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("Accent.TButton", font=("Segoe UI", 9, "bold"))
        style.configure("Hint.TLabel", foreground=P["off"])

    def _retint(self) -> None:
        """Перекрасить то, чего не касаются стили ttk: tk-виджеты, теги таблицы, заголовок окна."""
        theme.retint(self.root)
        self.dot.configure(background=P["bg"])
        self.tree.tag_configure("off", foreground=P["disabled"])
        self.tree.tag_configure("live", background=P["live_bg"])
        self.error_lbl.configure(foreground=P["error"])
        self.monitor._last = None  # монитор перерисуется новыми цветами на следующем опросе
        self._update_status()
        theme.set_titlebar(self.root, self._dark)

    def _set_theme(self, mode: str) -> None:
        if mode != self.cfg.settings.theme:
            self._commit(Config(self._settings(theme=mode), self.cfg.profiles), push=False)
        self._apply_theme()
        self._retint()

    def _build(self) -> None:
        root = self.root

        top = ttk.Frame(root, padding=(12, 10, 12, 4))
        top.pack(fill="x")
        self.dot = tk.Canvas(top, width=16, height=16, highlightthickness=0, bg=P["bg"])
        self.dot.pack(side="left")
        self.status = ttk.Label(top, text="", style="Status.TLabel")
        self.status.pack(side="left", padx=(6, 12))
        self.run_btn = ttk.Button(top, text="Включить", command=self.service.toggle, style="Accent.TButton")
        self.run_btn.pack(side="left")
        hk = ttk.Frame(top)
        hk.pack(side="right")
        ttk.Label(hk, text="Горячая клавиша вкл/выкл:").pack(side="left", padx=(0, 6))
        tk_ = self.cfg.settings.toggle_key
        self.hotkey = KeyField(hk, (tk_,) if tk_ else (), self._set_hotkey, combo=False, allow_empty=True,
                               on_capture=self._capture_hook, width=12)
        self.hotkey.pack(side="left")

        prof = ttk.Frame(root, padding=(12, 4))
        prof.pack(fill="x")
        ttk.Label(prof, text="Профиль:").pack(side="left")
        self.profile_cb = ttk.Combobox(prof, state="readonly", width=36)
        self.profile_cb.pack(side="left", padx=6)
        self.profile_cb.bind("<<ComboboxSelected>>", self._select_profile)
        mb = ttk.Menubutton(prof, text="Действия с профилем")
        menu = tk.Menu(mb, tearoff=False)
        menu.add_command(label="Новый пустой профиль…", command=self._profile_new)
        menu.add_command(label="Новый стандартный (PXN V9: руль как мышь)…", command=self._profile_new_default)
        menu.add_command(label="Новый: руль как геймпад Xbox…", command=self._profile_new_gamepad)
        menu.add_command(label="Копия текущего…", command=self._profile_copy)
        menu.add_command(label="Переименовать…", command=self._profile_rename)
        menu.add_command(label="Удалить", command=self._profile_delete)
        menu.add_separator()
        menu.add_command(label="Импорт из файла…", command=self._profile_import)
        menu.add_command(label="Экспорт в файл…", command=self._profile_export)
        mb["menu"] = menu
        mb.pack(side="left")

        paned = ttk.PanedWindow(root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=12, pady=8)
        left = ttk.Frame(paned)
        self.monitor = Monitor(paned, self.cfg.settings.monitor_device, self._monitor_select)
        paned.add(left, weight=3)
        paned.add(self.monitor, weight=2)

        cols = ("on", "name", "input", "action", "params")
        tree_box = ttk.Frame(left)
        tree_box.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_box, columns=cols, show="headings", selectmode="browse")
        for col, text, width, anchor in (("on", "Вкл", 44, "center"), ("name", "Название", 190, "w"),
                                         ("input", "Ввод с руля", 200, "w"), ("action", "Действие", 150, "w"),
                                         ("params", "Параметры", 190, "w")):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor=anchor, stretch=col != "on")
        sb = ttk.Scrollbar(tree_box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.tree.tag_configure("off", foreground=P["disabled"])
        self.tree.tag_configure("live", background=P["live_bg"])
        self.tree.bind("<Button-1>", self._tree_click)
        self.tree.bind("<Double-1>", self._tree_double)
        self.tree.bind("<Delete>", lambda _e: self._delete())
        self.tree.bind("<Return>", lambda _e: self._edit())

        bar = ttk.Frame(left, padding=(0, 8, 0, 0))
        bar.pack(fill="x")
        add = ttk.Menubutton(bar, text="＋ Добавить")
        amenu = tk.Menu(add, tearoff=False)
        for preset in PRESETS:
            if preset is None:
                amenu.add_separator()
            else:
                label, factory = preset
                amenu.add_command(label=label, command=lambda f=factory: self._add(f()))
        add["menu"] = amenu
        add.pack(side="left")
        for text, cmd in (("Изменить", self._edit), ("Копия", self._duplicate), ("Удалить", self._delete),
                          ("▲", lambda: self._move(-1)), ("▼", lambda: self._move(1))):
            ttk.Button(bar, text=text, command=cmd, width=10 if len(text) > 1 else 3).pack(side="left", padx=(6, 0))
        ttk.Label(bar, text="Подсвечено голубым — то, что сейчас срабатывает", style="Hint.TLabel").pack(
            side="right")

        bottom = ttk.Frame(root, padding=(12, 0, 12, 4))
        bottom.pack(fill="x")
        self.start_var = tk.BooleanVar(value=self.cfg.settings.start_enabled)
        ttk.Checkbutton(bottom, text="Включать маппинг сразу при запуске", variable=self.start_var,
                        command=self._set_start_enabled).pack(side="left")
        ttk.Label(bottom, text="Частота опроса, Гц:").pack(side="left", padx=(18, 4))
        self.tick_var = tk.StringVar(value=str(self.cfg.settings.tick_rate))
        spin = ttk.Spinbox(bottom, from_=TICK_RATE[0], to=TICK_RATE[1], increment=5, width=6,
                           textvariable=self.tick_var, command=self._set_tick)
        spin.bind("<FocusOut>", lambda _e: self._set_tick())
        spin.bind("<Return>", lambda _e: self._set_tick())
        spin.pack(side="left")
        ttk.Label(bottom, text="Тема:").pack(side="left", padx=(18, 4))
        self.theme_cb = Choice(bottom, theme.LABELS, self.cfg.settings.theme, self._set_theme, width=14)
        self.theme_cb.pack(side="left")
        ttk.Button(bottom, text="Папка настроек", command=self._open_data_dir).pack(side="right")
        ttk.Button(bottom, text="Ярлык в «Пуск»", command=self._make_shortcut).pack(side="right", padx=(0, 6))
        self.error_lbl = ttk.Label(bottom, text="", foreground=P["error"])
        self.error_lbl.pack(side="right", padx=12)

        pad_row = ttk.Frame(root, padding=(12, 0, 12, 10))
        pad_row.pack(fill="x")
        self.pad_lbl = ttk.Label(pad_row, text=f"Геймпад: {getattr(self.service, 'pad_status', 'не используется')}",
                                 style="Hint.TLabel")
        self.pad_lbl.pack(side="left")
        ttk.Label(pad_row, text="Вибрация из игры на руль:").pack(side="left", padx=(18, 4))
        # Метка создаётся раньше ползунка: Scale.set() сразу зовёт command.
        self.rumble_pct = ttk.Label(pad_row, width=5, text=f"{self.cfg.settings.rumble}%")
        self.rumble_scale = ttk.Scale(pad_row, from_=RUMBLE[0], to=RUMBLE[1], length=120,
                                      command=self._rumble_move)
        self.rumble_scale.set(self.cfg.settings.rumble)
        for ev in ("<ButtonRelease-1>", "<KeyRelease>"):
            self.rumble_scale.bind(ev, lambda _e: self._set_rumble())
        self.rumble_scale.pack(side="left")
        self.rumble_pct.pack(side="left", padx=(4, 0))
        self.rumble_test_btn = ttk.Button(pad_row, text="Проверить", command=self.service.rumble_test)
        self.rumble_test_btn.pack(side="left", padx=(4, 0))
        self.rumble_lbl = ttk.Label(pad_row, text=getattr(self.service, "rumble_status", ""), style="Hint.TLabel")
        self.rumble_lbl.pack(side="left", padx=(8, 0))

    # --- конфиг ---

    @property
    def profile(self) -> Profile:
        return self.cfg.active

    def _commit(self, cfg: Config, push: bool = True) -> None:
        self.cfg = Config.from_dict(cfg.to_dict())
        try:
            storage.save_config(self.cfg, self.cfg_path)
        except OSError as e:
            messagebox.showerror(APP_NAME, f"Не удалось сохранить настройки:\n{e}", parent=self.root)
        if push:
            self.service.set_profile(self.cfg.active)
        self._refresh_profiles()
        self._refresh_tree()

    def _settings(self, **kw) -> Settings:
        return Settings.from_dict(self.cfg.settings.to_dict() | kw)

    def _set_profile(self, profile: Profile, select: Optional[int] = None) -> None:
        active = self.cfg.settings.active_profile
        profiles = tuple(profile if p.name == active else p for p in self.cfg.profiles)
        self._commit(Config(self.cfg.settings, profiles))
        if select is not None and self.tree.exists(str(select)):
            self.tree.selection_set(str(select))
            self.tree.focus(str(select))
            self.tree.see(str(select))

    def _set_bindings(self, bindings: list[Binding], select: Optional[int] = None) -> None:
        self._set_profile(Profile(self.profile.name, tuple(bindings)), select)

    # --- список привязок ---

    def _refresh_tree(self) -> None:
        sel = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        names = self.service.device_names()
        for i, b in enumerate(self.profile.bindings):
            tags = () if b.enabled else ("off",)
            self.tree.insert("", "end", iid=str(i), tags=tags, values=(
                "✔" if b.enabled else "—", b.name, labels.source_text(b.source, names),
                labels.action_text(b.action), labels.params_text(b)))
        self._live.clear()
        if sel and self.tree.exists(sel[0]):
            self.tree.selection_set(sel[0])

    def _selected(self) -> Optional[int]:
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _tree_click(self, e):
        if self.tree.identify_region(e.x, e.y) == "cell" and self.tree.identify_column(e.x) == "#1":
            iid = self.tree.identify_row(e.y)
            if iid:
                bindings = list(self.profile.bindings)
                i = int(iid)
                b = bindings[i]
                bindings[i] = Binding.from_dict(b.to_dict() | {"enabled": not b.enabled})
                self._set_bindings(bindings, i)
                return "break"
        return None

    def _tree_double(self, e):
        # Второй быстрый клик Tk присылает как <Double-1>, а не <Button-1> — иначе он терялся.
        if self.tree.identify_column(e.x) == "#1":
            return self._tree_click(e)
        if self.tree.identify_row(e.y):
            self._edit()
        return "break"

    def _add(self, binding: Binding) -> None:
        dlg = BindingDialog(self, binding, "Новая привязка")
        if dlg.result:
            bindings = list(self.profile.bindings) + [dlg.result]
            self._set_bindings(bindings, len(bindings) - 1)

    def _edit(self) -> None:
        i = self._selected()
        if i is None:
            return
        dlg = BindingDialog(self, self.profile.bindings[i], "Изменить привязку")
        if dlg.result:
            bindings = list(self.profile.bindings)
            bindings[i] = dlg.result
            self._set_bindings(bindings, i)

    def _duplicate(self) -> None:
        i = self._selected()
        if i is None:
            return
        bindings = list(self.profile.bindings)
        b = bindings[i]
        bindings.insert(i + 1, Binding.from_dict(b.to_dict() | {"name": f"{b.name} (копия)"}))
        self._set_bindings(bindings, i + 1)

    def _delete(self) -> None:
        i = self._selected()
        if i is None:
            return
        b = self.profile.bindings[i]
        if not messagebox.askyesno(APP_NAME, f"Удалить привязку «{b.name}»?", parent=self.root):
            return
        bindings = list(self.profile.bindings)
        del bindings[i]
        self._set_bindings(bindings, min(i, len(bindings) - 1) if bindings else None)

    def _move(self, delta: int) -> None:
        i = self._selected()
        if i is None:
            return
        j = i + delta
        bindings = list(self.profile.bindings)
        if not 0 <= j < len(bindings):
            return
        bindings[i], bindings[j] = bindings[j], bindings[i]
        self._set_bindings(bindings, j)

    # --- профили ---

    def _refresh_profiles(self) -> None:
        names = [p.name for p in self.cfg.profiles]
        self.profile_cb["values"] = names
        self.profile_cb.current(names.index(self.profile.name))

    def _taken(self, exclude: str = "") -> set[str]:
        return {p.name for p in self.cfg.profiles if p.name != exclude}

    def _ask_name(self, title: str, initial: str, exclude: str = "") -> Optional[str]:
        raw = simpledialog.askstring(APP_NAME, title, initialvalue=initial, parent=self.root)
        if raw is None:
            return None
        name = clean_text(raw, "")
        if not name:
            messagebox.showerror(APP_NAME, "Имя не может быть пустым.", parent=self.root)
            return None
        if name in self._taken(exclude):
            messagebox.showerror(APP_NAME, f"Профиль «{name}» уже есть.", parent=self.root)
            return None
        return name

    def _add_profile(self, profile: Profile) -> None:
        if len(self.cfg.profiles) >= 64:
            messagebox.showerror(APP_NAME, "Слишком много профилей (максимум 64).", parent=self.root)
            return
        profiles = self.cfg.profiles + (profile,)
        self._commit(Config(self._settings(active_profile=profile.name), profiles))

    def _select_profile(self, _e=None) -> None:
        name = self.profile_cb.get()
        if name != self.cfg.settings.active_profile:
            self._commit(Config(self._settings(active_profile=name), self.cfg.profiles))

    def _profile_new(self) -> None:
        name = self._ask_name("Имя нового профиля:", unique_name("Новый профиль", self._taken()))
        if name:
            self._add_profile(Profile(name, ()))

    def _profile_new_default(self) -> None:
        base = default_profile()
        name = self._ask_name("Имя нового профиля:", unique_name(base.name, self._taken()))
        if name:
            self._add_profile(Profile(name, base.bindings))

    def _profile_new_gamepad(self) -> None:
        base = gamepad_profile()
        name = self._ask_name("Имя нового профиля:", unique_name(base.name, self._taken()))
        if name:
            self._add_profile(Profile(name, base.bindings))

    def _profile_copy(self) -> None:
        name = self._ask_name("Имя копии:", unique_name(f"{self.profile.name} (копия)", self._taken()))
        if name:
            self._add_profile(Profile(name, self.profile.bindings))

    def _profile_rename(self) -> None:
        old = self.profile.name
        name = self._ask_name("Новое имя профиля:", old, exclude=old)
        if not name or name == old:
            return
        profiles = tuple(Profile(name, p.bindings) if p.name == old else p for p in self.cfg.profiles)
        self._commit(Config(self._settings(active_profile=name), profiles), push=False)

    def _profile_delete(self) -> None:
        if len(self.cfg.profiles) <= 1:
            messagebox.showinfo(APP_NAME, "Это единственный профиль — его нельзя удалить.", parent=self.root)
            return
        old = self.profile.name
        if not messagebox.askyesno(APP_NAME, f"Удалить профиль «{old}»?", parent=self.root):
            return
        profiles = tuple(p for p in self.cfg.profiles if p.name != old)
        self._commit(Config(self._settings(active_profile=profiles[0].name), profiles))

    def _profile_import(self) -> None:
        path = filedialog.askopenfilename(parent=self.root, title="Импорт профиля",
                                          filetypes=[("Профиль WheelScript", "*.json"), ("Все файлы", "*.*")])
        if not path:
            return
        try:
            prof = storage.import_profile(Path(path))
        except (OSError, ValueError, UnicodeDecodeError, RecursionError) as e:
            messagebox.showerror(APP_NAME, f"Не удалось импортировать:\n{e}", parent=self.root)
            return
        self._add_profile(Profile(unique_name(prof.name, self._taken()), prof.bindings))

    def _profile_export(self) -> None:
        path = filedialog.asksaveasfilename(parent=self.root, title="Экспорт профиля", defaultextension=".json",
                                            initialfile=f"{self.profile.name}.json",
                                            filetypes=[("Профиль WheelScript", "*.json")])
        if not path:
            return
        try:
            storage.export_profile(self.profile, Path(path))
        except OSError as e:
            messagebox.showerror(APP_NAME, f"Не удалось сохранить:\n{e}", parent=self.root)

    # --- настройки ---

    def _capture_hook(self, active: bool) -> None:
        # пока ловим клавишу, горячая клавиша не должна переключать маппинг
        if active:
            self.service.suspend()
        else:
            self.service.resume()

    def _set_hotkey(self, value: tuple[str, ...]) -> None:
        name = value[-1] if value else ""
        self.service.set_toggle_key(name)
        self._commit(Config(self._settings(toggle_key=name), self.cfg.profiles), push=False)
        self._update_status()

    def _set_start_enabled(self) -> None:
        self._commit(Config(self._settings(start_enabled=bool(self.start_var.get())), self.cfg.profiles), push=False)

    def _set_tick(self) -> None:
        try:
            hz = int(float(self.tick_var.get()))
        except ValueError:
            hz = self.cfg.settings.tick_rate
        hz = max(TICK_RATE[0], min(TICK_RATE[1], hz))
        self.tick_var.set(str(hz))
        if hz != self.cfg.settings.tick_rate:
            self.service.set_tick_rate(hz)
            self._commit(Config(self._settings(tick_rate=hz), self.cfg.profiles), push=False)

    def _rumble_move(self, value) -> None:
        pct = int(round(float(value)))
        self.rumble_pct.configure(text=f"{pct}%")
        self.service.set_rumble(pct / 100)

    def _set_rumble(self) -> None:
        pct = max(RUMBLE[0], min(RUMBLE[1], int(round(float(self.rumble_scale.get())))))
        self._rumble_move(pct)
        if pct != self.cfg.settings.rumble:
            self._commit(Config(self._settings(rumble=pct), self.cfg.profiles), push=False)

    def _monitor_select(self, key: str) -> None:
        self._commit(Config(self._settings(monitor_device=key), self.cfg.profiles), push=False)

    def _make_shortcut(self) -> None:
        from . import shortcut
        try:
            path = shortcut.create()
        except Exception as e:  # noqa: BLE001
            log.exception("shortcut failed")
            messagebox.showerror(APP_NAME, f"Не удалось создать ярлык:\n{e}", parent=self.root)
            return
        messagebox.showinfo(APP_NAME, f"Ярлык создан в меню «Пуск»:\n{path}\n\n"
                                      f"Теперь {APP_NAME} находится через поиск Windows.", parent=self.root)

    def _open_data_dir(self) -> None:
        d = self.cfg_path.parent
        d.mkdir(parents=True, exist_ok=True)
        os.startfile(d)  # noqa: S606  (только Windows)

    # --- цикл обновления ---

    def _poll(self) -> None:
        if self._closing:
            return
        try:
            while True:
                ev = self.service.events.get_nowait()
                if ev[0] == "devices":
                    self._refresh_tree()
                elif ev[0] == "pad_status":
                    self.pad_lbl.configure(text=f"Геймпад: {ev[1]}")
                elif ev[0] == "rumble_status":
                    self.rumble_lbl.configure(text=ev[1])
                elif ev[0] == "error":
                    self._error = ev[1]
                    self.error_lbl.configure(text=f"Ошибка: {ev[1]}"[:120])
        except queue.Empty:
            pass
        try:
            states, infos = self.service.snapshot()
            self._infos = infos
            self.monitor.update_view(states, infos)
            self._update_live(states, infos)
            self._update_status()
            if self.cfg.settings.theme == "system":
                self._theme_polls += 1
                if self._theme_polls >= THEME_CHECK_POLLS:
                    self._theme_polls = 0
                    if theme.system_is_dark() != self._dark:  # в Windows переключили тему
                        self._apply_theme()
                        self._retint()
        except Exception:  # noqa: BLE001
            log.exception("ui poll failed")
        self.root.after(POLL_MS, self._poll)

    def _update_live(self, states, infos) -> None:
        default = infos[0].key if infos else None
        for i, b in enumerate(self.profile.bindings):
            iid = str(i)
            v = binding_value(b, states, default) if b.enabled else None
            if v is None:
                live = False
            elif b.action.is_analog:
                live = shape(abs(v), b.deadzone, b.curve) > 0
            else:
                live = abs(v) >= b.threshold
            if self._live.get(iid) != live and self.tree.exists(iid):
                self._live[iid] = live
                tags = [t for t in self.tree.item(iid, "tags") if t != "live"]
                if live:
                    tags.append("live")
                self.tree.item(iid, tags=tags)

    def _update_status(self) -> None:
        hk = self.cfg.settings.toggle_key
        suffix = f" ({keys.display(hk)})" if hk else ""
        if not self._infos:
            text, color = "Руль не найден", P["off"]
        elif self.service.enabled:
            text, color = "Маппинг ВКЛЮЧЁН", P["on"]
        else:
            text, color = "Маппинг выключен", P["off"]
        self.status.configure(text=text, foreground=color)
        self.dot.delete("all")
        self.dot.create_oval(2, 2, 14, 14, fill=color, outline="")
        self.run_btn.configure(text=("Выключить" if self.service.enabled else "Включить") + suffix)

    def close(self) -> None:
        self._closing = True
        try:
            self.service.stop()
        finally:
            self.root.destroy()
