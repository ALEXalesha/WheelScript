"""Поля ввода: выпадающий список с ключами, захват с руля, захват клавиш."""

from __future__ import annotations

import time
from typing import Callable, Optional

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QPushButton, QWidget

from .. import keys, labels
from ..capture import Capture
from ..model import InputSource
from ..theme import P
from . import dialogs

CAPTURE_TIMEOUT = 15.0
CAPTURE_POLL_MS = 15


class Choice(QComboBox):
    """Выпадающий список: показывает подписи, хранит ключи."""
    key_changed = Signal(str)

    def __init__(self, mapping: dict[str, str], value: str,
                 command: Optional[Callable[[str], None]] = None, parent=None):
        super().__init__(parent)
        self._keys = list(mapping)
        for k in self._keys:
            self.addItem(mapping[k], k)
        self.set_key(value)
        self.activated.connect(lambda _i: self.key_changed.emit(self.get_key()))
        if command:
            self.key_changed.connect(command)

    def get_key(self) -> str:
        i = self.currentIndex()
        return self._keys[i] if 0 <= i < len(self._keys) else self._keys[0]

    def set_key(self, key: str) -> None:
        self.setCurrentIndex(self._keys.index(key) if key in self._keys else 0)


class _CaptureLine(QLineEdit):
    """Нередактируемое поле: щелчок запускает захват, клавиши уходят владельцу."""
    clicked = Signal()

    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setReadOnly(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.ClickFocus)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def event(self, event):
        # Во время захвата Tab — тоже клавиша, а не переход к следующему полю.
        if event.type() in (QEvent.KeyPress, QEvent.KeyRelease) and self.owner.capturing:
            if event.type() == QEvent.KeyPress:
                self.owner.key_pressed(event)
            else:
                self.owner.key_released(event)
            event.accept()
            return True
        if event.type() == QEvent.ShortcutOverride and self.owner.capturing:
            event.accept()  # никакие сочетания окна не срабатывают, пока ловим клавишу
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self.owner.capturing:
            return  # обработано в event()
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.owner.focus_lost()


def _paint_waiting(line: QLineEdit, waiting: bool) -> None:
    if waiting:
        line.setStyleSheet(f"QLineEdit {{ background: {P['wait_bg']}; color: {P['entry_fg']}; }}")
    else:
        line.setStyleSheet("")


class InputField(QWidget):
    """Поле «ввод с руля»: щелчок — и первая нажатая кнопка/ось/крестовина попадает в поле."""
    source_changed = Signal(object)

    def __init__(self, service, source: InputSource, parent=None):
        super().__init__(parent)
        self.service = service
        self.source = source
        self._capture: Optional[Capture] = None
        self._deadline = 0.0
        self.line = _CaptureLine(self)
        self.line.clicked.connect(self.start)
        self.clear_button = QPushButton("Сбросить")
        self.clear_button.clicked.connect(self.clear)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.line, 1)
        lay.addWidget(self.clear_button)
        self.timer = QTimer(self)
        self.timer.setInterval(CAPTURE_POLL_MS)
        self.timer.timeout.connect(self._poll)
        self.refresh()

    @property
    def capturing(self) -> bool:
        return self._capture is not None

    def refresh(self) -> None:
        if self._capture:
            return
        if self.source.is_set:
            self.line.setText(labels.source_text(self.source, self.service.device_names()))
        else:
            self.line.setText("щёлкни сюда и нажми кнопку / сдвинь ось на руле")

    def start(self) -> None:
        if self._capture:
            return
        states, infos = self.service.snapshot()
        if not infos:
            dialogs.warning(self.window(), "Руль не подключён — нечего считывать.")
            return
        self._capture = Capture(states)
        self._deadline = time.monotonic() + CAPTURE_TIMEOUT
        _paint_waiting(self.line, True)
        self.line.setText("жду: нажми кнопку, сдвинь ось или крестовину…  (Esc — отмена)")
        self.line.setFocus()
        self.timer.start()

    def _poll(self) -> None:
        if not self._capture:
            self.timer.stop()
            return
        states, _ = self.service.snapshot()
        found = self._capture.feed(states)
        if found is not None:
            self._stop()
            self.source = found
            self.source_changed.emit(found)
            self.refresh()
            return
        if time.monotonic() > self._deadline:
            self.cancel()

    def _stop(self) -> None:
        self.timer.stop()
        self._capture = None
        _paint_waiting(self.line, False)

    def cancel(self) -> None:
        self._stop()
        self.refresh()

    def clear(self) -> None:
        self._stop()
        self.source = InputSource()
        self.source_changed.emit(self.source)
        self.refresh()

    def set_source(self, src: InputSource) -> None:
        self.source = src
        self.refresh()

    # клавиатура во время захвата: только Esc
    def key_pressed(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.cancel()

    def key_released(self, event) -> None:
        pass

    def focus_lost(self) -> None:
        pass  # руль можно трогать, даже если окно потеряло фокус


class KeyField(QWidget):
    """Поле клавиши: щелчок — нажми клавишу/сочетание. Плюс выбор из списка и «✕»."""
    value_changed = Signal(tuple)
    capture_changed = Signal(bool)  # True — начали ловить, False — закончили

    def __init__(self, value: tuple[str, ...], combo: bool = True, allow_empty: bool = False,
                 parent=None):
        super().__init__(parent)
        self.value = tuple(value)
        self.combo = combo
        self.allow_empty = allow_empty
        self._capturing = False
        self._down: set[str] = set()
        self._collected: list[str] = []
        self.line = _CaptureLine(self)
        self.line.clicked.connect(self.start)
        self._names = list(keys.KEY_NAMES)
        self.pick = QComboBox()
        self.pick.addItem("выбрать…")
        for n in self._names:
            self.pick.addItem(keys.display(n))
        self.pick.activated.connect(self._picked)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.line, 1)
        lay.addWidget(self.pick)
        self.clear_button = None
        if allow_empty:
            self.clear_button = QPushButton("✕")
            self.clear_button.setFixedWidth(32)
            self.clear_button.setToolTip("Без клавиши")
            self.clear_button.clicked.connect(lambda: self._set(()))
            lay.addWidget(self.clear_button)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.finish)
        self.refresh()

    @property
    def capturing(self) -> bool:
        return self._capturing

    def refresh(self) -> None:
        if not self._capturing:
            self.line.setText(keys.combo_text(self.value) if self.value else "нет")

    def start(self) -> None:
        if self._capturing:
            return
        self._capturing = True
        self._down.clear()
        self._collected.clear()
        self.capture_changed.emit(True)
        _paint_waiting(self.line, True)
        self.line.setText("нажми клавишу" + (" или сочетание" if self.combo else "") + "…  (Esc — отмена)")
        self.line.setFocus()
        self.timer.start(int(CAPTURE_TIMEOUT * 1000))

    @staticmethod
    def name_of(event) -> Optional[str]:
        return keys.from_native(event.nativeVirtualKey(), event.nativeScanCode(),
                                keys.is_extended(event.nativeModifiers()))

    def key_pressed(self, event) -> None:
        if event.isAutoRepeat():
            return
        name = self.name_of(event)
        if name == "esc" and not self._down and not self._collected:
            self.finish(cancel=True)
            return
        if name:
            self._down.add(name)
            if name not in self._collected:
                self._collected.append(name)

    def key_released(self, event) -> None:
        if event.isAutoRepeat():
            return
        name = self.name_of(event)
        if name and name not in self._collected:  # PrintScreen приходит только отпусканием
            self._collected.append(name)
        self._down.discard(name)
        if not self._down and self._collected:
            self.finish()

    def focus_lost(self) -> None:
        self.finish()

    def finish(self, cancel: bool = False) -> None:
        if not self._capturing:
            return
        self._capturing = False
        self.timer.stop()
        _paint_waiting(self.line, False)
        self.capture_changed.emit(False)
        combo = keys.normalize_combo(self._collected)
        if not cancel and combo:
            self._set(combo if self.combo else combo[-1:])
        self.refresh()

    def _picked(self, i: int) -> None:
        self.pick.setCurrentIndex(0)
        if i > 0:
            self._set((self._names[i - 1],))

    def _set(self, value: tuple[str, ...]) -> None:
        if not value and not self.allow_empty:
            return
        self.value = tuple(value)
        self.value_changed.emit(self.value)
        self.refresh()

    def set_value(self, value: tuple[str, ...]) -> None:
        self.value = tuple(value)
        self.refresh()
