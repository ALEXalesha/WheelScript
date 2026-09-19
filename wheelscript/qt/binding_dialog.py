"""Редактор одной привязки. Пока открыт, маппинг на паузе, чтобы руль не «кликал» по окну."""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QDialog, QDoubleSpinBox, QGridLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QSlider, QVBoxLayout, QWidget)

from .. import labels
from ..capture import adapt_source
from ..engine import binding_value, shape
from ..model import (ANALOG_ACTIONS, DEFAULT_MOVE_SPEED, DEFAULT_WHEEL_SPEED, MOVE_SPEED, WHEEL_SPEED,
                     Binding, InputSource)
from ..theme import P
from . import dialogs
from .fields import Choice, InputField, KeyField

log = logging.getLogger(__name__)

POLL_MS = 40
KINDS = ("key", "mouse_button", "mouse_move", "mouse_wheel", "pad_button", "pad_stick", "pad_trigger", "toggle")
SLIDER_STEPS = 1000


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()


class Preview(QWidget):
    """Полоска проверки: что сейчас приходит с руля и сработает ли привязка."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(26)
        self.binding: Optional[Binding] = None
        self.value: Optional[float] = None

    def show_value(self, binding: Binding, value: Optional[float]) -> None:
        self.binding, self.value = binding, value
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(P["surface"]))
        p.setPen(QPen(QColor(P["border"])))
        p.setBrush(QColor(P["surface2"]))
        p.drawRect(QRectF(1, 4, w - 2, h - 8))
        b, v = self.binding, self.value
        if b is None or v is None:
            p.end()
            return
        inner = w - 2
        signed = b.source.kind == "axis" and b.source.mode == "full"
        if b.action.is_analog:
            m = shape(abs(v), b.deadzone, b.curve) * (1 if v >= 0 else -1)
            if signed:
                mid = w / 2
                p.fillRect(QRectF(min(mid, mid + m * mid), 4, abs(m * mid), h - 8), QColor(P["accent"]))
                p.setPen(QColor(P["tick"]))
                p.drawLine(int(mid), 2, int(mid), h - 2)
            else:
                p.fillRect(QRectF(1, 4, abs(m) * inner, h - 8), QColor(P["accent"]))
        else:
            mag = abs(v)
            active = mag >= b.threshold
            p.fillRect(QRectF(1, 4, mag * inner, h - 8), QColor(P["on"] if active else P["accent"]))
            if b.source.kind == "axis":
                tx = 1 + b.threshold * inner
                p.setPen(QPen(QColor(P["error"]), 2))
                p.drawLine(int(tx), 0, int(tx), h)
        p.end()


class Tune:
    """Ползунок тонкой настройки с подписью значения."""

    def __init__(self, value: float, lo: float, hi: float, fmt):
        self.lo, self.hi, self.fmt = lo, hi, fmt
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, SLIDER_STEPS)
        self.label = QLabel()
        self.label.setMinimumWidth(48)
        self.label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.slider.valueChanged.connect(lambda _v: self.label.setText(self.fmt(self.value)))
        self.set(value)

    @property
    def value(self) -> float:
        return self.lo + (self.hi - self.lo) * self.slider.value() / SLIDER_STEPS

    def set(self, value: float) -> None:
        value = min(self.hi, max(self.lo, value))
        self.slider.setValue(round((value - self.lo) / (self.hi - self.lo) * SLIDER_STEPS))
        self.label.setText(self.fmt(self.value))


class BindingDialog(QDialog):
    def __init__(self, parent, service, binding: Binding, title: str):
        super().__init__(parent)
        self.service = service
        self.result_binding: Optional[Binding] = None
        self.setWindowTitle(title)
        self.setModal(True)
        self._resumed = False
        service.suspend()

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
        self.move_speed = a.speed if a.kind == "mouse_move" else DEFAULT_MOVE_SPEED
        self.wheel_speed = a.speed if a.kind == "mouse_wheel" else DEFAULT_WHEEL_SPEED
        self.threshold = Tune(binding.threshold, 0.01, 0.99, lambda v: f"{v:.0%}")
        self.deadzone = Tune(binding.deadzone, 0.0, 0.5, lambda v: f"{v:.0%}")
        self.curve = Tune(binding.curve, 0.2, 3.0, lambda v: f"{v:.2f}")
        self.invert = QCheckBox("Инвертировать")
        self.invert.setChecked(binding.invert)
        self.enabled = QCheckBox("Привязка включена")
        self.enabled.setChecked(binding.enabled)

        root = QVBoxLayout(self)
        form = QGridLayout()
        form.setColumnStretch(1, 1)
        form.setColumnMinimumWidth(0, 150)
        root.addLayout(form)

        self.name = QLineEdit(binding.name)
        form.addWidget(QLabel("Название"), 0, 0)
        form.addWidget(self.name, 0, 1)

        self.input = InputField(service, binding.source)
        self.input.source_changed.connect(self._on_source)
        form.addWidget(QLabel("Ввод с руля"), 1, 0)
        form.addWidget(self.input, 1, 1)

        self.mode_label = QLabel("")
        self.axis_mode = Choice(labels.AXIS_MODE_LABELS,
                                binding.source.mode if binding.source.kind == "axis" else "full")
        self.hat_mode = Choice(labels.HAT_DIR_LABELS,
                               binding.source.mode if binding.source.kind == "hat" else "up")
        mode_box = QHBoxLayout()
        mode_box.setContentsMargins(0, 0, 0, 0)
        mode_box.addWidget(self.axis_mode)
        mode_box.addWidget(self.hat_mode)
        mode_box.addStretch(1)
        form.addWidget(self.mode_label, 2, 0)
        form.addLayout(mode_box, 2, 1)

        self.kind = Choice({k: labels.ACTION_LABELS[k] for k in KINDS},
                           a.kind if a.kind in KINDS else "key", self._on_kind)
        form.addWidget(QLabel("Действие"), 3, 0)
        kind_box = QHBoxLayout()
        kind_box.addWidget(self.kind)
        kind_box.addStretch(1)
        form.addLayout(kind_box, 3, 1)

        self.params = QGridLayout()
        self.params.setColumnStretch(1, 1)
        self.params.setColumnMinimumWidth(0, 150)
        root.addLayout(self.params)

        self._tune_captions: list[QLabel] = []
        self.tune_box = QGroupBox("Тонкая настройка")
        self.tune = QGridLayout(self.tune_box)
        self.tune.setColumnStretch(1, 1)
        self.tune.setColumnMinimumWidth(0, 150)
        root.addWidget(self.tune_box)

        pv = QGroupBox("Проверка — покрути / нажми на руле")
        pv_lay = QVBoxLayout(pv)
        self.preview = Preview()
        self.preview_text = QLabel("")
        pv_lay.addWidget(self.preview)
        pv_lay.addWidget(self.preview_text)
        root.addWidget(pv)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.save_button = QPushButton("Сохранить")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.accept_binding)
        self.cancel_button = QPushButton("Отмена")
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.cancel_button)
        root.addLayout(buttons)

        self._build_params()
        self._update_mode_row()
        self._build_tune()
        self.setMinimumWidth(640)

        self.timer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    # --- построение ---

    def _row(self, r: int, text: str, widget: QWidget) -> None:
        self.params.addWidget(QLabel(text), r, 0)
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(widget)
        lay.addStretch(1)
        self.params.addWidget(box, r, 1)

    def _hint(self, r: int, text: str) -> None:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {P['off']};")
        self.params.addWidget(lbl, r, 0, 1, 2)

    def _speed(self, value: float, lo: float, hi: float, step: float, suffix: str, setter) -> QWidget:
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        spin = QDoubleSpinBox()
        spin.setDecimals(0)
        spin.setRange(lo, hi)
        spin.setSingleStep(step)
        spin.setValue(value)
        spin.valueChanged.connect(setter)
        lay.addWidget(spin)
        lay.addWidget(QLabel(suffix))
        return box

    def _build_params(self) -> None:
        _clear(self.params)
        self.key_field = None
        k = self.kind.get_key()
        if k == "key":
            self.key_field = KeyField(self.keys_val)
            self.key_field.value_changed.connect(self._set_keys)
            self._row(0, "Клавиша", self.key_field)
            self._row(1, "Режим нажатия", Choice(labels.PRESS_LABELS, self.press_val, self._set_press))
        elif k == "mouse_button":
            self._row(0, "Кнопка мыши", Choice(labels.MOUSE_BUTTON_LABELS, self.button_val, self._set_button))
            self._row(1, "Режим нажатия", Choice(labels.PRESS_LABELS, self.press_val, self._set_press))
        elif k == "mouse_move":
            self._row(0, "Направление", Choice(labels.DIRECTION_LABELS, self.move_dir, self._set_move_dir))
            self._row(1, "Скорость", self._speed(self.move_speed, MOVE_SPEED[0], MOVE_SPEED[1], 50,
                                                 "пикселей в секунду при полном отклонении",
                                                 self._set_move_speed))
        elif k == "mouse_wheel":
            self._row(0, "Направление", Choice(labels.DIRECTION_LABELS, self.wheel_dir, self._set_wheel_dir))
            self._row(1, "Скорость", self._speed(self.wheel_speed, 1, WHEEL_SPEED[1], 1,
                                                 "щелчков колеса в секунду", self._set_wheel_speed))
        elif k in ("pad_button", "pad_stick", "pad_trigger"):
            if k == "pad_button":
                self._row(0, "Кнопка геймпада",
                          Choice(labels.PAD_BUTTON_LABELS, self.pad_button_val, self._set_pad_button))
                self._row(1, "Режим нажатия", Choice(labels.PRESS_LABELS, self.press_val, self._set_press))
            elif k == "pad_stick":
                self._row(0, "Стик", Choice(labels.PAD_STICK_LABELS, self.stick_val, self._set_stick))
                self._row(1, "Направление", Choice(labels.DIRECTION_LABELS, self.stick_dir, self._set_stick_dir))
            else:
                self._row(0, "Курок", Choice(labels.PAD_TRIGGER_LABELS, self.trigger_val, self._set_trigger))
            self._hint(2, "Игра увидит виртуальный геймпад Xbox 360 (нужен драйвер ViGEmBus).")
        else:
            self._hint(0, "Нажатие включает или выключает весь маппинг — то же, что горячая клавиша.")

    def _tune_row(self, r: int, text: str, tune: Tune) -> None:
        caption = QLabel(text)
        self._tune_captions.append(caption)
        self.tune.addWidget(caption, r, 0)
        self.tune.addWidget(tune.slider, r, 1)
        self.tune.addWidget(tune.label, r, 2)

    def _build_tune(self) -> None:
        # ползунки и галочки переиспользуются (в них настройки): убираем из сетки и прячем;
        # подписи создаются заново
        while self.tune.count():
            item = self.tune.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
        for caption in self._tune_captions:
            caption.setParent(None)
            caption.deleteLater()
        self._tune_captions = []
        r = 0
        is_axis = self.input.source.kind == "axis"
        analog = self.kind.get_key() in ANALOG_ACTIONS
        shown = []
        if analog and is_axis:
            self._tune_row(r, "Мёртвая зона", self.deadzone)
            self._tune_row(r + 1, "Кривая (1 = линейно)", self.curve)
            shown += [self.deadzone, self.curve]
            r += 2
        elif is_axis:
            self._tune_row(r, "Порог срабатывания", self.threshold)
            shown.append(self.threshold)
            r += 1
        self.tune.addWidget(self.invert, r, 0)
        self.tune.addWidget(self.enabled, r, 1)
        for t in shown:
            t.slider.show()
            t.label.show()
        self.invert.show()
        self.enabled.show()

    def visible_tunes(self) -> list[str]:
        names = {id(self.deadzone.slider): "deadzone", id(self.curve.slider): "curve",
                 id(self.threshold.slider): "threshold"}
        return [names[id(t.slider)] for t in (self.deadzone, self.curve, self.threshold)
                if self.tune.indexOf(t.slider) >= 0]

    def _update_mode_row(self) -> None:
        self.axis_mode.hide()
        self.hat_mode.hide()
        kind = self.input.source.kind
        if kind == "axis":
            self.axis_mode.set_key(self.input.source.mode)
            self.mode_label.setText("Как читать ось")
            self.axis_mode.show()
        elif kind == "hat":
            self.hat_mode.set_key(self.input.source.mode)
            self.mode_label.setText("Направление")
            self.hat_mode.show()
        else:
            self.mode_label.setText("")

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
    def _set_move_speed(self, v): self.move_speed = float(v)
    def _set_wheel_speed(self, v): self.wheel_speed = float(v)

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
            direction, speed = self.move_dir, self.move_speed
        elif k == "mouse_wheel":
            direction, speed = self.wheel_dir, self.wheel_speed
        elif k == "pad_stick":
            direction, speed = self.stick_dir, DEFAULT_MOVE_SPEED
        else:
            direction, speed = "right", DEFAULT_MOVE_SPEED
        pad = {"pad_button": self.pad_button_val, "pad_stick": self.stick_val,
               "pad_trigger": self.trigger_val}.get(k, "")
        return Binding.from_dict({
            "name": self.name.text(),
            "source": self._current_source().to_dict(),
            "action": {"kind": k, "keys": list(self.keys_val), "button": self.button_val,
                       "direction": direction, "speed": speed, "press": self.press_val, "pad": pad},
            "enabled": self.enabled.isChecked(),
            "threshold": self.threshold.value,
            "deadzone": self.deadzone.value,
            "curve": self.curve.value,
            "invert": self.invert.isChecked(),
        })

    def _tick(self) -> None:
        try:
            states, infos = self.service.snapshot()
            b = self.build()
            v = binding_value(b, states, infos[0].key if infos else None)
            self.show_preview(b, v)
        except Exception:  # noqa: BLE001
            log.exception("preview failed")

    def show_preview(self, b: Binding, v: Optional[float]) -> None:
        self.preview.show_value(b, v)
        if v is None:
            text, color = "нет данных: ввод не назначен или ось ещё не двигалась", P["off"]
        elif b.action.is_analog:
            m = shape(abs(v), b.deadzone, b.curve)
            text, color = f"значение {v:+.2f} → сила {m:.0%}", P["on"] if m else P["off"]
        else:
            active = abs(v) >= b.threshold
            text = ("СРАБОТАЛО" if active else "не нажато") + f"  ({abs(v):.0%})"
            color = P["on"] if active else P["off"]
        self.preview_text.setText(text)
        self.preview_text.setStyleSheet(f"color: {color};")

    # --- закрытие ---

    def accept_binding(self) -> None:
        b = self.build()
        if b.action.kind == "key" and not b.action.keys:
            dialogs.error(self, "Выбери клавишу.")
            return
        if not b.source.is_set and not dialogs.yes_no(
                self, "Ввод с руля не назначен — привязка не будет срабатывать. Сохранить так?"):
            return
        self.result_binding = b
        self.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self.input.capturing:
            self.input.cancel()  # Esc сначала отменяет захват, а не закрывает окно
            return
        super().keyPressEvent(event)

    def done(self, result: int) -> None:
        self.timer.stop()
        if self.input.capturing:
            self.input.cancel()
        if self.key_field is not None and self.key_field.capturing:
            self.key_field.finish(cancel=True)
        if not self._resumed:
            self._resumed = True
            self.service.resume()
        super().done(result)
