"""
Движок маппинга. Чистая логика без WinAPI: состояние устройств + dt на вход,
список событий на выход.

События:
    ("key", name, down)         клавиша
    ("mouse", button, down)     кнопка мыши
    ("move", dx, dy)            относительное движение мыши, целые пиксели
    ("wheel", delta, horizontal) прокрутка, кратно 120
    ("enabled", flag)           маппинг включён/выключен
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Mapping, Optional

from .model import Action, Binding, InputSource, Profile

TAP_SECONDS = 0.05   # короче игры, опрашивающие клавиатуру раз в кадр, могут пропустить нажатие
MAX_DT = 0.1         # после зависания/сна не выстреливаем гигантским рывком мыши
MAX_TAP_QUEUE = 32
HYSTERESIS = 0.05
WHEEL_DELTA = 120

MOVE_VEC = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}
WHEEL_VEC = {"up": (1, False), "down": (-1, False), "right": (1, True), "left": (-1, True)}


@dataclass(frozen=True)
class DeviceState:
    # None в axes — ось ещё ни разу не присылала значение (SDL до первого движения
    # отдаёт 0.0, а у педалей покой = -1, поэтому доверять этому 0.0 нельзя).
    axes: tuple[Optional[float], ...] = ()
    buttons: tuple[bool, ...] = ()
    hats: tuple[tuple[int, int], ...] = ()


States = Mapping[str, DeviceState]


def _finite(x: object) -> Optional[float]:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    x = float(x)
    return x if math.isfinite(x) else None


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def read_source(src: InputSource, states: States, default_device: Optional[str] = None) -> Optional[float]:
    """Нормализованное значение источника: full -> [-1, 1], остальное -> [0, 1], None — нет данных."""
    if src.kind == "none":
        return None
    key = src.device or default_device
    if not key:
        return None
    st = states.get(key)
    if st is None:
        return None
    i = src.index
    if src.kind == "axis":
        if not 0 <= i < len(st.axes):
            return None
        raw = _finite(st.axes[i])
        if raw is None:
            return None
        raw = _clamp(raw, -1.0, 1.0)
        mode = src.mode
        if mode == "pos":
            return max(raw, 0.0)
        if mode == "neg":
            return max(-raw, 0.0)
        if mode == "pedal":
            return (raw + 1.0) / 2.0
        if mode == "pedal_inv":
            return (1.0 - raw) / 2.0
        return raw
    if src.kind == "button":
        if not 0 <= i < len(st.buttons):
            return None
        return 1.0 if st.buttons[i] else 0.0
    if src.kind == "hat":
        if not 0 <= i < len(st.hats):
            return None
        hx, hy = st.hats[i]
        hit = {"up": hy > 0, "down": hy < 0, "left": hx < 0, "right": hx > 0}.get(src.mode, False)
        return 1.0 if hit else 0.0
    return None


def is_signed(src: InputSource) -> bool:
    return src.kind == "axis" and src.mode == "full"


def binding_value(b: Binding, states: States, default_device: Optional[str] = None) -> Optional[float]:
    v = read_source(b.source, states, default_device)
    if v is None:
        return None
    if b.invert:
        v = -v if is_signed(b.source) else 1.0 - v
    return v


def shape(mag: float, deadzone: float, curve: float) -> float:
    """|отклонение| -> [0, 1] с мёртвой зоной и степенной кривой."""
    m = _finite(mag)
    if m is None:
        return 0.0
    m = _clamp(m, 0.0, 1.0)
    dz = _clamp(_finite(deadzone) or 0.0, 0.0, 0.95)
    c = _clamp(_finite(curve) or 1.0, 0.2, 5.0)
    if m <= dz:
        return 0.0
    return _clamp(((m - dz) / (1.0 - dz)) ** c, 0.0, 1.0)


def release_level(threshold: float) -> float:
    return threshold - min(HYSTERESIS, threshold / 2.0)


class Engine:
    def __init__(self, profile: Optional[Profile] = None, enabled: bool = False):
        self._bindings: tuple[Binding, ...] = tuple(profile.bindings) if profile else ()
        self._enabled = enabled
        self._active: dict[int, bool] = {}
        self._on: dict[int, bool] = {}
        self._latched: dict[int, bool] = {}
        self._tap_left: dict[int, float] = {}
        self._tap_queue: dict[int, int] = {}
        self._blocked: set[int] = set()
        self._keys: Counter[str] = Counter()
        self._buttons: Counter[str] = Counter()
        self._acc = [0.0, 0.0]
        self._wacc = [0.0, 0.0]

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def bindings(self) -> tuple[Binding, ...]:
        return self._bindings

    def held_keys(self) -> frozenset[str]:
        return frozenset(k for k, c in self._keys.items() if c > 0)

    def held_buttons(self) -> frozenset[str]:
        return frozenset(k for k, c in self._buttons.items() if c > 0)

    # --- управление ---

    def set_profile(self, profile: Profile, states: Optional[States] = None,
                    default_device: Optional[str] = None) -> list:
        events = self._release_outputs()
        self._bindings = tuple(profile.bindings)
        self._active.clear()
        self._blocked.clear()
        if states is not None:
            self.block_active(states, default_device)
        return events

    def set_enabled(self, flag: bool) -> list:
        if flag == self._enabled:
            return []
        self._enabled = flag
        events = [] if flag else self._release_outputs()
        events.append(("enabled", flag))
        return events

    def release_all(self) -> list:
        return self._release_outputs()

    def block_active(self, states: States, default_device: Optional[str] = None) -> None:
        """Всё, что сейчас зажато на руле, игнорируется до отпускания.

        Нужно после паузы (например, пока открыт редактор привязки): иначе кнопка,
        которую держат в момент возврата, сразу «нажмётся».
        """
        for i, b in enumerate(self._bindings):
            if b.action.is_analog:
                continue
            v = binding_value(b, states, default_device)
            if v is not None and abs(v) >= b.threshold:
                self._active[i] = True
                self._blocked.add(i)

    # --- основной шаг ---

    def step(self, states: States, dt: float, default_device: Optional[str] = None) -> list:
        dt = _clamp(_finite(dt) or 0.0, 0.0, MAX_DT)
        events: list = []
        mx = my = wv = wh = 0.0

        for i, b in enumerate(self._bindings):
            a = b.action
            if not b.enabled or a.kind == "none":
                continue
            v = binding_value(b, states, default_device)

            if a.is_analog:
                if not self._enabled or v is None:
                    continue
                m = shape(abs(v), b.deadzone, b.curve)
                if v < 0:
                    m = -m
                amount = m * a.speed * dt
                if a.kind == "mouse_move":
                    vx, vy = MOVE_VEC[a.direction]
                    mx += vx * amount
                    my += vy * amount
                else:
                    sign, horizontal = WHEEL_VEC[a.direction]
                    if horizontal:
                        wh += sign * amount
                    else:
                        wv += sign * amount
                continue

            if v is None:
                self._tap_queue.pop(i, None)  # устройство пропало — отложенные тапы не проигрываем
            mag = 0.0 if v is None else abs(v)
            was = self._active.get(i, False)
            now = mag >= (release_level(b.threshold) if was else b.threshold)
            self._active[i] = now
            rising = now and not was

            if i in self._blocked:
                if now:
                    continue
                self._blocked.discard(i)

            if a.kind == "toggle":
                if rising:
                    events += self.set_enabled(not self._enabled)
                continue
            if not self._enabled:
                continue

            want = self._want(i, a.press, now, rising, dt)
            on = self._on.get(i, False)
            if want and not on:
                self._press(a, events)
                self._on[i] = True
            elif on and not want:
                self._release(a, events)
                self._on[i] = False

        if self._enabled:
            ix, iy = self._accumulate(self._acc, mx, my)
            if ix or iy:
                events.append(("move", ix, iy))
            nv, nh = self._accumulate(self._wacc, wv, wh)
            if nv:
                events.append(("wheel", nv * WHEEL_DELTA, False))
            if nh:
                events.append(("wheel", nh * WHEEL_DELTA, True))
        return events

    # --- внутреннее ---

    @staticmethod
    def _accumulate(acc: list[float], x: float, y: float) -> tuple[int, int]:
        out = []
        for k, total in enumerate((x, y)):
            if total == 0.0:
                acc[k] = 0.0  # остаток прошлого движения не должен «догонять» потом
                out.append(0)
                continue
            acc[k] += total
            whole = int(acc[k])  # к нулю, симметрично для + и -
            acc[k] -= whole
            out.append(whole)
        return out[0], out[1]

    def _want(self, i: int, press: str, now: bool, rising: bool, dt: float) -> bool:
        if press == "toggle":
            if rising:
                self._latched[i] = not self._latched.get(i, False)
            return self._latched.get(i, False)
        if press == "tap":
            # Каждое нажатие — отдельный тап не короче TAP_SECONDS. Нажатие во время
            # текущего тапа не продлевает его, а встаёт в очередь (иначе оно терялось).
            on = self._on.get(i, False)
            if rising and on:
                self._tap_queue[i] = min(self._tap_queue.get(i, 0) + 1, MAX_TAP_QUEUE)
            if on:
                left = self._tap_left.get(i, 0.0) - dt
                self._tap_left[i] = max(left, 0.0)
                return left > 0.0
            if rising or self._tap_queue.get(i, 0) > 0:
                if not rising:
                    self._tap_queue[i] -= 1
                self._tap_left[i] = TAP_SECONDS
                return True
            return False
        return now

    def _press(self, a: Action, events: list) -> None:
        if a.kind == "key":
            for k in dict.fromkeys(a.keys):
                if self._keys[k] == 0:
                    events.append(("key", k, True))
                self._keys[k] += 1
        elif a.kind == "mouse_button":
            if self._buttons[a.button] == 0:
                events.append(("mouse", a.button, True))
            self._buttons[a.button] += 1

    def _release(self, a: Action, events: list) -> None:
        if a.kind == "key":
            for k in reversed(list(dict.fromkeys(a.keys))):
                c = self._keys[k] - 1
                if c <= 0:
                    self._keys.pop(k, None)
                    events.append(("key", k, False))
                else:
                    self._keys[k] = c
        elif a.kind == "mouse_button":
            c = self._buttons[a.button] - 1
            if c <= 0:
                self._buttons.pop(a.button, None)
                events.append(("mouse", a.button, False))
            else:
                self._buttons[a.button] = c

    def _release_outputs(self) -> list:
        events: list = []
        for i, on in list(self._on.items()):
            if on and i < len(self._bindings):
                self._release(self._bindings[i].action, events)
        self._on.clear()
        self._latched.clear()
        self._tap_left.clear()
        self._tap_queue.clear()
        for k in list(self._keys):
            events.append(("key", k, False))
        for b in list(self._buttons):
            events.append(("mouse", b, False))
        self._keys.clear()
        self._buttons.clear()
        self._acc = [0.0, 0.0]
        self._wacc = [0.0, 0.0]
        return events
