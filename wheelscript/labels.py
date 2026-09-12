"""Человекочитаемые подписи для интерфейса."""

from __future__ import annotations

from typing import Mapping, Optional

from . import keys
from .model import Action, Binding, InputSource

AXIS_MODE_LABELS = {
    "full": "вся ось (−1…+1)",
    "pos": "только в + сторону",
    "neg": "только в − сторону",
    "pedal": "педаль (покой = −1)",
    "pedal_inv": "педаль (покой = +1)",
}
HAT_LABELS = {"up": "↑", "down": "↓", "left": "←", "right": "→"}
HAT_DIR_LABELS = {"up": "вверх ↑", "down": "вниз ↓", "left": "влево ←", "right": "вправо →"}
ACTION_LABELS = {
    "key": "Клавиша / сочетание",
    "mouse_button": "Кнопка мыши",
    "mouse_move": "Движение мыши",
    "mouse_wheel": "Колесо мыши",
    "pad_button": "Кнопка геймпада",
    "pad_stick": "Стик геймпада",
    "pad_trigger": "Курок геймпада (LT/RT)",
    "toggle": "Вкл/выкл маппинг",
    "none": "Ничего",
}
PAD_BUTTON_LABELS = {
    "a": "A", "b": "B", "x": "X", "y": "Y",
    "lb": "LB (левый бампер)", "rb": "RB (правый бампер)",
    "back": "Back / View", "start": "Start / Menu",
    "ls": "Нажатие левого стика (LS)", "rs": "Нажатие правого стика (RS)",
    "guide": "Guide (кнопка Xbox)",
    "dup": "Крестовина ↑", "ddown": "Крестовина ↓", "dleft": "Крестовина ←", "dright": "Крестовина →",
}
PAD_STICK_LABELS = {"left": "левый стик", "right": "правый стик"}
PAD_TRIGGER_LABELS = {"lt": "LT (левый курок)", "rt": "RT (правый курок)"}
MOUSE_BUTTON_LABELS = {
    "left": "ЛКМ", "right": "ПКМ", "middle": "СКМ (колесо)",
    "x1": "Боковая X1 (назад)", "x2": "Боковая X2 (вперёд)",
}
DIRECTION_LABELS = {"left": "влево", "right": "вправо", "up": "вверх", "down": "вниз"}
PRESS_LABELS = {
    "hold": "держать, пока нажато",
    "tap": "одно короткое нажатие",
    "toggle": "залипание (нажал — вкл, ещё раз — выкл)",
}


def source_text(src: InputSource, device_names: Optional[Mapping[str, str]] = None) -> str:
    if src.kind == "none":
        return "—"
    if src.kind == "axis":
        text = f"Ось {src.index}, {AXIS_MODE_LABELS.get(src.mode, src.mode)}"
    elif src.kind == "button":
        text = f"Кнопка {src.index}"
    else:
        text = f"Крестовина {src.index} {HAT_LABELS.get(src.mode, src.mode)}"
    if src.device and device_names is not None and len(device_names) > 1:
        text += f" [{device_names.get(src.device, 'не подключено')}]"
    elif src.device and device_names is not None and src.device not in device_names:
        text += " [не подключено]"
    return text


def action_text(a: Action) -> str:
    if a.kind == "key":
        return f"Клавиша {keys.combo_text(a.keys)}"
    if a.kind == "mouse_button":
        return MOUSE_BUTTON_LABELS.get(a.button, a.button)
    if a.kind == "mouse_move":
        return f"Мышь {DIRECTION_LABELS.get(a.direction, a.direction)}"
    if a.kind == "mouse_wheel":
        return f"Колесо {DIRECTION_LABELS.get(a.direction, a.direction)}"
    if a.kind == "pad_button":
        return f"Геймпад {PAD_BUTTON_LABELS.get(a.pad, a.pad)}"
    if a.kind == "pad_stick":
        return f"Геймпад: {PAD_STICK_LABELS.get(a.pad, a.pad)} {DIRECTION_LABELS.get(a.direction, a.direction)}"
    if a.kind == "pad_trigger":
        return f"Геймпад {PAD_TRIGGER_LABELS.get(a.pad, a.pad)}"
    return ACTION_LABELS.get(a.kind, a.kind)


def params_text(b: Binding) -> str:
    a = b.action
    parts = []
    if a.kind == "mouse_move":
        parts.append(f"{a.speed:g} пикс/с")
    elif a.kind == "mouse_wheel":
        parts.append(f"{a.speed:g} щелч/с")
    if a.is_analog and b.source.kind == "axis":
        if b.deadzone:
            parts.append(f"мёртв. зона {b.deadzone:.0%}")
        if b.curve != 1.0:
            parts.append(f"кривая {b.curve:g}")
    elif not a.is_analog and b.source.kind == "axis":
        parts.append(f"порог {b.threshold:.0%}")
    if a.kind in ("key", "mouse_button", "pad_button") and a.press != "hold":
        parts.append({"tap": "одно нажатие", "toggle": "залипание"}[a.press])
    if b.invert:
        parts.append("инверсия")
    return ", ".join(parts)
