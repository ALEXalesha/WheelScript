"""Живой вид всех осей, кнопок и крестовин выбранного устройства."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QComboBox, QGroupBox, QVBoxLayout, QWidget

from ..theme import P

ARROWS = {(0, 1): "↑", (0, -1): "↓", (-1, 0): "←", (1, 0): "→",
          (1, 1): "↗", (-1, 1): "↖", (1, -1): "↘", (-1, -1): "↙"}
AXIS_ROW = 20
BUTTON = 30
BUTTON_STEP = 34


def monitor_height(state, width: int) -> int:
    """Сколько места нужно, чтобы нарисовать состояние целиком."""
    if state is None:
        return 120
    cols = max(1, int((width - 16) // BUTTON_STEP))
    rows = (len(state.buttons) + cols - 1) // cols
    return 8 + len(state.axes) * AXIS_ROW + 6 + 18 + rows * 26 + 8 + len(state.hats) * 20 + 8


class MonitorCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = None
        self.setMinimumSize(260, 200)
        self.setAttribute(Qt.WA_OpaquePaintEvent)

    def set_state(self, state) -> None:
        self.state = state
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(P["surface"]))
        p.setPen(QPen(QColor(P["border"])))
        p.drawRect(0, 0, w - 1, h - 1)
        st = self.state
        if st is None:
            p.setPen(QColor(P["off"]))
            p.drawText(QRectF(0, 30, w, 60), Qt.AlignHCenter | Qt.AlignTop,
                       "Руль не найден.\nПодключи его — список обновится сам.")
            return
        small = QFont(self.font())
        small.setPointSizeF(max(6.0, self.font().pointSizeF() - 2))
        y = 8
        x0, x1 = 58, w - 58
        mid = (x0 + x1) / 2
        for i, v in enumerate(st.axes):
            p.setPen(QColor(P["text"]))
            p.drawText(QRectF(8, y, 50, 16), Qt.AlignVCenter | Qt.AlignLeft, f"Ось {i}")
            p.setPen(QColor(P["border"]))
            p.setBrush(QColor(P["surface2"]))
            p.drawRect(QRectF(x0, y + 2, x1 - x0, 12))
            if v is None:
                p.setFont(small)
                p.setPen(QColor(P["faint"]))
                p.drawText(QRectF(x0, y, x1 - x0, 16), Qt.AlignCenter, "ещё не двигалась")
                p.setFont(self.font())
            else:
                xv = mid + v * (x1 - x0) / 2
                p.fillRect(QRectF(min(mid, xv), y + 2, abs(xv - mid), 12), QColor(P["accent"]))
                p.setPen(QColor(P["faint"]))
                p.drawLine(int(mid), y, int(mid), y + 16)
                p.setPen(QColor(P["text"]))
                p.drawText(QRectF(x1, y, w - 8 - x1, 16), Qt.AlignVCenter | Qt.AlignRight, f"{v:+.2f}")
            y += AXIS_ROW
        y += 6
        p.setPen(QColor(P["text"]))
        p.drawText(QRectF(8, y, w - 16, 16), Qt.AlignLeft | Qt.AlignTop, "Кнопки")
        y += 18
        cols = max(1, int((w - 16) // BUTTON_STEP))
        for i, pressed in enumerate(st.buttons):
            r, col = divmod(i, cols)
            x, yy = 8 + col * BUTTON_STEP, y + r * 26
            p.setPen(QColor(P["border"]))
            p.setBrush(QColor(P["accent"] if pressed else P["surface2"]))
            p.drawRoundedRect(QRectF(x, yy, BUTTON, 22), 3, 3)
            p.setPen(QColor("#ffffff" if pressed else P["text"]))
            p.drawText(QRectF(x, yy, BUTTON, 22), Qt.AlignCenter, str(i))
        y += ((len(st.buttons) + cols - 1) // cols) * 26 + 8
        p.setPen(QColor(P["text"]))
        for i, hat in enumerate(st.hats):
            p.drawText(QRectF(8, y, w - 16, 18), Qt.AlignLeft | Qt.AlignTop,
                       f"Крестовина {i}:  {ARROWS.get(tuple(hat), '·')}")
            y += 20
        p.end()


class Monitor(QGroupBox):
    device_selected = Signal(str)

    def __init__(self, selected: str, parent=None):
        super().__init__("Что сейчас нажато на руле", parent)
        self._selected = selected
        self._devices: list[str] = []
        self._last = None
        self.device = QComboBox()
        self.device.activated.connect(self._changed)
        self.canvas = MonitorCanvas()
        lay = QVBoxLayout(self)
        lay.addWidget(self.device)
        lay.addWidget(self.canvas, 1)

    def _changed(self, i: int) -> None:
        if 0 <= i < len(self._devices):
            self._selected = self._devices[i]
            self.device_selected.emit(self._selected)

    def current_key(self) -> Optional[str]:
        if self._selected in self._devices:
            return self._selected
        return self._devices[0] if self._devices else None

    def update_view(self, states, infos) -> bool:
        """Обновить вид. True — если что-то поменялось и холст перерисуется."""
        keys_ = [d.key for d in infos]
        if keys_ != self._devices:
            self._devices = keys_
            self.device.clear()
            self.device.addItems([d.name for d in infos] or ["(руль не найден)"])
            key = self.current_key()
            self.device.setCurrentIndex(keys_.index(key) if key in keys_ else 0)
        key = self.current_key()
        st = states.get(key) if key else None
        sig = (key, st)
        if sig == self._last:
            return False
        self._last = sig
        self.canvas.set_state(st)
        return True

    def repaint_colors(self) -> None:
        self._last = None
        self.canvas.update()
