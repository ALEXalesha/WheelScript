"""
Модель данных: источник ввода, действие, привязка, профиль, конфиг.

Всё неизменяемое (frozen dataclass). from_dict() принимает что угодно
(в т.ч. битый/чужой JSON) и всегда возвращает валидный объект в
каноническом виде, поэтому to_dict -> from_dict — тождественное преобразование.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from . import keys as keymod

SOURCE_KINDS = ("none", "axis", "button", "hat")
AXIS_MODES = ("full", "pos", "neg", "pedal", "pedal_inv")
HAT_DIRS = ("up", "down", "left", "right")
ACTION_KINDS = ("none", "key", "mouse_button", "mouse_move", "mouse_wheel",
                "pad_button", "pad_stick", "pad_trigger", "toggle")
MOTION_ACTIONS = frozenset({"mouse_move", "mouse_wheel"})
PAD_ACTIONS = frozenset({"pad_button", "pad_stick", "pad_trigger"})
ANALOG_ACTIONS = MOTION_ACTIONS | {"pad_stick", "pad_trigger"}
PRESS_ACTIONS = frozenset({"key", "mouse_button", "pad_button"})
MOUSE_BUTTONS = ("left", "right", "middle", "x1", "x2")
PAD_BUTTONS = ("a", "b", "x", "y", "lb", "rb", "back", "start", "ls", "rs", "guide",
               "dup", "ddown", "dleft", "dright")
PAD_STICKS = ("left", "right")
PAD_TRIGGERS = ("lt", "rt")
DIRECTIONS = ("left", "right", "up", "down")
PRESS_MODES = ("hold", "tap", "toggle")

THRESHOLD = (0.01, 0.99)
DEADZONE = (0.0, 0.95)
CURVE = (0.2, 5.0)
MOVE_SPEED = (0.0, 50000.0)
WHEEL_SPEED = (0.0, 200.0)
TICK_RATE = (20, 1000)
RUMBLE = (0, 100)
THEMES = ("system", "light", "dark")
DEFAULT_MOVE_SPEED = 1500.0
DEFAULT_WHEEL_SPEED = 10.0

MAX_NAME = 80
MAX_DEVICE = 100
MAX_INDEX = 255
MAX_COMBO = 4
MAX_BINDINGS = 256
MAX_PROFILES = 64
CONFIG_VERSION = 1


def _num(x: Any, default: float, lo: float, hi: float) -> float:
    if isinstance(x, bool):
        return default
    if isinstance(x, str):
        try:
            x = float(x)
        except ValueError:
            return default
    if not isinstance(x, (int, float)):
        return default
    try:
        x = float(x)
    except OverflowError:
        return default
    if not math.isfinite(x):
        return default
    return min(max(x, lo), hi)


def _int(x: Any, default: int, lo: int, hi: int) -> int:
    v = _num(x, float(default), float(lo), float(hi))
    return int(v)


def _choice(x: Any, choices: tuple[str, ...], default: str) -> str:
    return x if isinstance(x, str) and x in choices else default


def _bool(x: Any, default: bool) -> bool:
    return x if isinstance(x, bool) else default


def clean_text(x: Any, default: str = "", maxlen: int = MAX_NAME) -> str:
    """Убирает управляющие символы и одиночные суррогаты (их не запишет json в UTF-8)."""
    if not isinstance(x, str):
        return default
    s = "".join(ch if ch.isprintable() else " " for ch in x)
    s = " ".join(s.split())[:maxlen].strip()
    return s or default


@dataclass(frozen=True)
class InputSource:
    kind: str = "none"
    index: int = 0
    mode: str = ""
    device: str = ""

    @staticmethod
    def axis(index: int, mode: str = "full", device: str = "") -> "InputSource":
        return InputSource.from_dict({"kind": "axis", "index": index, "mode": mode, "device": device})

    @staticmethod
    def button(index: int, device: str = "") -> "InputSource":
        return InputSource.from_dict({"kind": "button", "index": index, "device": device})

    @staticmethod
    def hat(index: int, direction: str, device: str = "") -> "InputSource":
        return InputSource.from_dict({"kind": "hat", "index": index, "mode": direction, "device": device})

    @staticmethod
    def from_dict(d: Any) -> "InputSource":
        if not isinstance(d, dict):
            return InputSource()
        kind = _choice(d.get("kind"), SOURCE_KINDS, "none")
        if kind == "none":
            return InputSource()
        index = _int(d.get("index"), 0, 0, MAX_INDEX)
        device = clean_text(d.get("device"), "", MAX_DEVICE)
        if kind == "axis":
            mode = _choice(d.get("mode"), AXIS_MODES, "full")
        elif kind == "hat":
            mode = _choice(d.get("mode"), HAT_DIRS, "up")
        else:
            mode = ""
        return InputSource(kind, index, mode, device)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "index": self.index, "mode": self.mode, "device": self.device}

    @property
    def is_set(self) -> bool:
        return self.kind != "none"


@dataclass(frozen=True)
class Action:
    kind: str = "none"
    keys: tuple[str, ...] = ()
    button: str = "left"
    direction: str = "right"
    speed: float = DEFAULT_MOVE_SPEED
    press: str = "hold"
    pad: str = ""  # кнопка / стик / курок геймпада, для остальных действий пусто

    @staticmethod
    def key(keys: tuple[str, ...] | list[str], press: str = "hold") -> "Action":
        return Action.from_dict({"kind": "key", "keys": list(keys), "press": press})

    @staticmethod
    def mouse(button: str, press: str = "hold") -> "Action":
        return Action.from_dict({"kind": "mouse_button", "button": button, "press": press})

    @staticmethod
    def move(direction: str, speed: float = DEFAULT_MOVE_SPEED) -> "Action":
        return Action.from_dict({"kind": "mouse_move", "direction": direction, "speed": speed})

    @staticmethod
    def wheel(direction: str, speed: float = DEFAULT_WHEEL_SPEED) -> "Action":
        return Action.from_dict({"kind": "mouse_wheel", "direction": direction, "speed": speed})

    @staticmethod
    def toggle() -> "Action":
        return Action(kind="toggle")

    @staticmethod
    def pad_button(button: str, press: str = "hold") -> "Action":
        return Action.from_dict({"kind": "pad_button", "pad": button, "press": press})

    @staticmethod
    def stick(stick: str, direction: str) -> "Action":
        return Action.from_dict({"kind": "pad_stick", "pad": stick, "direction": direction})

    @staticmethod
    def trigger(which: str) -> "Action":
        return Action.from_dict({"kind": "pad_trigger", "pad": which})

    @staticmethod
    def from_dict(d: Any) -> "Action":
        if not isinstance(d, dict):
            return Action()
        kind = _choice(d.get("kind"), ACTION_KINDS, "none")
        if kind == "key":
            raw = d.get("keys")
            combo = keymod.normalize_combo(raw if isinstance(raw, (list, tuple)) else (), MAX_COMBO)
            return Action(kind, keys=combo, press=_choice(d.get("press"), PRESS_MODES, "hold"))
        if kind == "mouse_button":
            return Action(kind, button=_choice(d.get("button"), MOUSE_BUTTONS, "left"),
                          press=_choice(d.get("press"), PRESS_MODES, "hold"))
        if kind == "mouse_move":
            return Action(kind, direction=_choice(d.get("direction"), DIRECTIONS, "right"),
                          speed=_num(d.get("speed"), DEFAULT_MOVE_SPEED, *MOVE_SPEED))
        if kind == "mouse_wheel":
            return Action(kind, direction=_choice(d.get("direction"), DIRECTIONS, "up"),
                          speed=_num(d.get("speed"), DEFAULT_WHEEL_SPEED, *WHEEL_SPEED))
        if kind == "pad_button":
            return Action(kind, pad=_choice(d.get("pad"), PAD_BUTTONS, "a"),
                          press=_choice(d.get("press"), PRESS_MODES, "hold"))
        if kind == "pad_stick":
            return Action(kind, pad=_choice(d.get("pad"), PAD_STICKS, "left"),
                          direction=_choice(d.get("direction"), DIRECTIONS, "right"))
        if kind == "pad_trigger":
            return Action(kind, pad=_choice(d.get("pad"), PAD_TRIGGERS, "rt"))
        return Action(kind)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "keys": list(self.keys), "button": self.button,
                "direction": self.direction, "speed": self.speed, "press": self.press, "pad": self.pad}

    @property
    def is_analog(self) -> bool:
        return self.kind in ANALOG_ACTIONS


@dataclass(frozen=True)
class Binding:
    name: str = "Привязка"
    source: InputSource = field(default_factory=InputSource)
    action: Action = field(default_factory=Action)
    enabled: bool = True
    threshold: float = 0.5
    deadzone: float = 0.05
    curve: float = 1.0
    invert: bool = False

    @staticmethod
    def make(name: str, source: InputSource, action: Action, **kw: Any) -> "Binding":
        return Binding.from_dict(Binding(name, source, action).to_dict() | kw)

    @staticmethod
    def from_dict(d: Any) -> "Binding":
        if not isinstance(d, dict):
            return Binding()
        return Binding(
            name=clean_text(d.get("name"), "Привязка"),
            source=InputSource.from_dict(d.get("source")),
            action=Action.from_dict(d.get("action")),
            enabled=_bool(d.get("enabled"), True),
            threshold=_num(d.get("threshold"), 0.5, *THRESHOLD),
            deadzone=_num(d.get("deadzone"), 0.05, *DEADZONE),
            curve=_num(d.get("curve"), 1.0, *CURVE),
            invert=_bool(d.get("invert"), False),
        )

    def to_dict(self) -> dict:
        return {"name": self.name, "source": self.source.to_dict(), "action": self.action.to_dict(),
                "enabled": self.enabled, "threshold": self.threshold, "deadzone": self.deadzone,
                "curve": self.curve, "invert": self.invert}


@dataclass(frozen=True)
class Profile:
    name: str = "Профиль"
    bindings: tuple[Binding, ...] = ()

    @staticmethod
    def from_dict(d: Any) -> "Profile":
        if not isinstance(d, dict):
            return Profile()
        raw = d.get("bindings")
        items = raw if isinstance(raw, list) else []
        bindings = tuple(Binding.from_dict(b) for b in items if isinstance(b, dict))[:MAX_BINDINGS]
        return Profile(clean_text(d.get("name"), "Профиль"), bindings)

    def to_dict(self) -> dict:
        return {"name": self.name, "bindings": [b.to_dict() for b in self.bindings]}


@dataclass(frozen=True)
class Settings:
    toggle_key: str = "f8"
    tick_rate: int = 125
    start_enabled: bool = False
    active_profile: str = ""
    monitor_device: str = ""
    rumble: int = 100  # сила вибрации из игры на руле, %; 0 — выключено
    theme: str = "system"

    @staticmethod
    def from_dict(d: Any) -> "Settings":
        if not isinstance(d, dict):
            return Settings()
        tk = d.get("toggle_key", "f8")
        th = d.get("theme")
        return Settings(
            toggle_key=tk if (tk == "" or keymod.is_key(tk)) else "f8",
            tick_rate=_int(d.get("tick_rate"), 125, *TICK_RATE),
            start_enabled=_bool(d.get("start_enabled"), False),
            active_profile=clean_text(d.get("active_profile"), ""),
            monitor_device=clean_text(d.get("monitor_device"), "", MAX_DEVICE),
            rumble=_int(d.get("rumble"), 100, *RUMBLE),
            theme=th if isinstance(th, str) and th in THEMES else "system",
        )

    def to_dict(self) -> dict:
        return {"toggle_key": self.toggle_key, "tick_rate": self.tick_rate,
                "start_enabled": self.start_enabled, "active_profile": self.active_profile,
                "monitor_device": self.monitor_device, "rumble": self.rumble, "theme": self.theme}


def unique_name(name: str, taken: set[str] | frozenset[str]) -> str:
    if name not in taken:
        return name
    n = 2
    while True:
        suffix = f" ({n})"
        candidate = name[: MAX_NAME - len(suffix)] + suffix
        if candidate not in taken:
            return candidate
        n += 1


@dataclass(frozen=True)
class Config:
    settings: Settings = field(default_factory=Settings)
    profiles: tuple[Profile, ...] = ()

    @staticmethod
    def from_dict(d: Any) -> "Config":
        if not isinstance(d, dict):
            d = {}
        raw = d.get("profiles")
        profiles: list[Profile] = []
        taken: set[str] = set()
        for p in raw if isinstance(raw, list) else []:
            if not isinstance(p, dict) or len(profiles) >= MAX_PROFILES:
                continue
            prof = Profile.from_dict(p)
            name = unique_name(prof.name, taken)
            taken.add(name)
            profiles.append(Profile(name, prof.bindings))
        if not profiles:
            profiles = [default_profile()]
        settings = Settings.from_dict(d.get("settings"))
        if settings.active_profile not in {p.name for p in profiles}:
            settings = Settings(**(settings.to_dict() | {"active_profile": profiles[0].name}))
        return Config(settings, tuple(profiles))

    def to_dict(self) -> dict:
        return {"version": CONFIG_VERSION, "settings": self.settings.to_dict(),
                "profiles": [p.to_dict() for p in self.profiles]}

    @property
    def active(self) -> Profile:
        for p in self.profiles:
            if p.name == self.settings.active_profile:
                return p
        return self.profiles[0]


def default_profile() -> Profile:
    """Раскладка под PXN V9 Gen 2 (ось 0 — руль, 2 — газ, 5 — тормоз, 6 — сцепление)."""
    B, S, A = Binding.make, InputSource, Action
    return Profile("Руль как мышь + W/S", (
        B("Поворот камеры (руль)", S.axis(0, "full"), A.move("right", 2250), deadzone=0.03),
        B("Газ → W", S.axis(2, "pedal"), A.key(["w"]), threshold=0.15),
        B("Тормоз → S", S.axis(5, "pedal"), A.key(["s"]), threshold=0.15),
        B("Камера вверх (крестовина ↑)", S.hat(0, "up"), A.move("up", 1500)),
        B("Камера вниз (крестовина ↓)", S.hat(0, "down"), A.move("down", 1500)),
        B("A → ЛКМ", S.button(0), A.mouse("left")),
        B("B → ПКМ", S.button(1), A.mouse("right")),
    ))


def gamepad_profile() -> Profile:
    """Руль как виртуальный геймпад Xbox 360: руль — левый стик, педали — курки."""
    B, S, A = Binding.make, InputSource, Action
    return Profile("Руль как геймпад (Xbox)", (
        B("Руль → левый стик", S.axis(0, "full"), A.stick("left", "right"), deadzone=0.02),
        B("Газ → RT", S.axis(2, "pedal"), A.trigger("rt"), deadzone=0.02),
        B("Тормоз → LT", S.axis(5, "pedal"), A.trigger("lt"), deadzone=0.02),
        B("A → A", S.button(0), A.pad_button("a")),
        B("B → B", S.button(1), A.pad_button("b")),
        B("Крестовина ↑", S.hat(0, "up"), A.pad_button("dup")),
        B("Крестовина ↓", S.hat(0, "down"), A.pad_button("ddown")),
        B("Крестовина ←", S.hat(0, "left"), A.pad_button("dleft")),
        B("Крестовина →", S.hat(0, "right"), A.pad_button("dright")),
    ))


def default_config() -> Config:
    return Config.from_dict({})
