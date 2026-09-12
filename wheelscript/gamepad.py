"""
Виртуальный геймпад Xbox 360 через драйвер ViGEmBus (пакет vgamepad).

vgamepad подключается к драйверу прямо при импорте и падает, если драйвера нет,
поэтому импорт ленивый и в try: без драйвера остальной маппинг работает как обычно.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from .engine import PadState

log = logging.getLogger(__name__)

# Биты XUSB_GAMEPAD_* из XInput.
BITS = {
    "dup": 0x0001, "ddown": 0x0002, "dleft": 0x0004, "dright": 0x0008,
    "start": 0x0010, "back": 0x0020, "ls": 0x0040, "rs": 0x0080,
    "lb": 0x0100, "rb": 0x0200, "guide": 0x0400,
    "a": 0x1000, "b": 0x2000, "x": 0x4000, "y": 0x8000,
}


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if not x >= lo else hi if x > hi else x  # NaN -> lo


def report_values(state: PadState) -> tuple[int, int, int, int, int, int, int]:
    """(кнопки, LT, RT, LX, LY, RX, RY) в формате XUSB_REPORT: WORD, BYTE x2, SHORT x4."""
    buttons = 0
    for b in state.buttons:
        buttons |= BITS.get(b, 0)

    def axis(v: float) -> int:
        return round(_clamp(v, -1.0, 1.0) * 32767)

    def trig(v: float) -> int:
        return round(_clamp(v, 0.0, 1.0) * 255)

    return (buttons, trig(state.lt), trig(state.rt),
            axis(state.lx), axis(state.ly), axis(state.rx), axis(state.ry))


def explain(e: BaseException) -> str:
    text = str(e)
    if isinstance(e, ImportError):
        return "нет пакета vgamepad"
    if "BUS_NOT_FOUND" in text:
        return "не установлен драйвер ViGEmBus"
    if "BUS_VERSION_MISMATCH" in text:
        return "устаревший драйвер ViGEmBus — обновите его"
    return text or e.__class__.__name__


class VirtualPad:
    """Создаёт геймпад при первой необходимости; если драйвера нет — пробует снова раз в RETRY секунд."""

    RETRY = 5.0

    def __init__(self, on_status: Callable[[str], None] = lambda s: None):
        self.on_status = on_status
        self.status = "не используется"
        self._pad = None
        self._next_try = 0.0

    @property
    def connected(self) -> bool:
        return self._pad is not None

    def _set_status(self, text: str) -> None:
        if text != self.status:
            self.status = text
            log.info("gamepad: %s", text)
            self.on_status(text)

    def _ensure(self):
        if self._pad is not None:
            return self._pad
        now = time.monotonic()
        if now < self._next_try:
            return None
        self._next_try = now + self.RETRY
        try:
            import vgamepad
            self._pad = vgamepad.VX360Gamepad()
        except Exception as e:  # noqa: BLE001 — vgamepad бросает голый Exception
            self._set_status(f"недоступен: {explain(e)}")
            return None
        self._set_status("подключён (Xbox 360)")
        return self._pad

    def apply(self, state: PadState) -> None:
        pad = self._ensure()
        if pad is None:
            return
        b, lt, rt, lx, ly, rx, ry = report_values(state)
        r = pad.report
        r.wButtons, r.bLeftTrigger, r.bRightTrigger = b, lt, rt
        r.sThumbLX, r.sThumbLY, r.sThumbRX, r.sThumbRY = lx, ly, rx, ry
        try:
            pad.update()
        except Exception as e:  # noqa: BLE001
            self._pad = None
            self._set_status(f"отключился: {explain(e)}")

    def close(self) -> None:
        pad, self._pad = self._pad, None
        if pad is None:
            return
        try:
            pad.reset()
            pad.update()
        except Exception:  # noqa: BLE001
            pass
        del pad  # __del__ у vgamepad отключает виртуальное устройство


def status_hint(status: Optional[str]) -> str:
    return f"Геймпад: {status or 'не используется'}"
