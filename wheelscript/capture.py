"""Определение нажатой кнопки / сдвинутой оси для поля «ввод с руля»."""

from __future__ import annotations

from typing import Optional

from .engine import DeviceState, States
from .model import InputSource

AXIS_THRESHOLD = 0.5
PEDAL_REST = 0.75
# Для этих действий руль нужен целиком: влево — в одну сторону, вправо — в другую.
# Курок сюда не входит: он от 0 до 1, половина оси или педаль ему подходят как есть.
WHOLE_AXIS_ACTIONS = frozenset({"mouse_move", "mouse_wheel", "pad_stick"})


class Capture:
    """Запоминает состояние в момент клика по полю и ждёт первое заметное изменение.

    Кнопка, зажатая уже в момент старта, не считается: сначала её надо отпустить.
    Ось, которая ещё ни разу не присылала данных (None), при первом значении
    только обновляет базу — иначе педаль, «прыгнувшая» из 0 в -1, выглядела бы нажатой.
    """

    def __init__(self, baseline: States, axis_threshold: float = AXIS_THRESHOLD):
        self.threshold = axis_threshold
        self._base: dict[str, DeviceState] = dict(baseline)

    def feed(self, states: States) -> Optional[InputSource]:
        for dev, st in states.items():
            base = self._base.get(dev)
            if base is None:
                self._base[dev] = st
                continue
            found = self._check(dev, base, st)
            if found:
                return found
        return None

    def _check(self, dev: str, base: DeviceState, st: DeviceState) -> Optional[InputSource]:
        bb = list(base.buttons)
        for i, pressed in enumerate(st.buttons):
            was = bb[i] if i < len(bb) else False
            if pressed and not was:
                return InputSource.button(i, dev)
            if not pressed and was:
                bb[i] = False

        bh = list(base.hats)
        for i, (hx, hy) in enumerate(st.hats):
            ox, oy = bh[i] if i < len(bh) else (0, 0)
            if hx != ox and hx != 0:
                return InputSource.hat(i, "right" if hx > 0 else "left", dev)
            if hy != oy and hy != 0:
                return InputSource.hat(i, "up" if hy > 0 else "down", dev)
            if (hx, hy) != (ox, oy):
                if i < len(bh):
                    bh[i] = (hx, hy)

        ba = list(base.axes)
        for i, v in enumerate(st.axes):
            if v is None:
                continue
            b = ba[i] if i < len(ba) else None
            if b is None:
                if i < len(ba):
                    ba[i] = v
                else:
                    ba.extend([None] * (i - len(ba)) + [v])
                continue
            delta = v - b
            if abs(delta) >= self.threshold:
                if b <= -PEDAL_REST:
                    mode = "pedal"
                elif b >= PEDAL_REST:
                    mode = "pedal_inv"
                else:
                    mode = "pos" if delta > 0 else "neg"
                return InputSource.axis(i, mode, dev)

        self._base[dev] = DeviceState(tuple(ba), tuple(bb), tuple(bh))
        return None


def adapt_source(src: InputSource, action_kind: str) -> InputSource:
    """Для движения мыши/колеса/стика ось руля нужна целиком (-1..+1), а не половина."""
    if src.kind == "axis" and src.mode in ("pos", "neg") and action_kind in WHOLE_AXIS_ACTIONS:
        return InputSource.axis(src.index, "full", src.device)
    return src
