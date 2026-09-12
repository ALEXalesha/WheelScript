"""Шаблоны для кнопки «Добавить»: готовое действие, ввод с руля назначается кликом."""

from __future__ import annotations

from typing import Callable, Optional

from .model import Action, Binding, InputSource

B, S, A = Binding.make, InputSource, Action
NONE = S()

Preset = Optional[tuple[str, Callable[[], Binding]]]

PRESETS: list[Preset] = [
    ("Руль → поворот камеры (мышь влево/вправо)",
     lambda: B("Поворот камеры", S.axis(0, "full"), A.move("right", 2250), deadzone=0.03)),
    ("Кнопка → камера вверх (мышь вверх)", lambda: B("Камера вверх", NONE, A.move("up", 1500))),
    ("Кнопка → камера вниз (мышь вниз)", lambda: B("Камера вниз", NONE, A.move("down", 1500))),
    ("Кнопка → мышь влево", lambda: B("Мышь влево", NONE, A.move("left", 1500))),
    ("Кнопка → мышь вправо", lambda: B("Мышь вправо", NONE, A.move("right", 1500))),
    None,
    ("Педаль → клавиша (держать)", lambda: B("Педаль → W", NONE, A.key(["w"]), threshold=0.15)),
    ("Кнопка → клавиша (держать)", lambda: B("Клавиша", NONE, A.key(["e"]))),
    ("Кнопка → клавиша (одно нажатие)", lambda: B("Нажатие клавиши", NONE, A.key(["e"], "tap"))),
    ("Кнопка → сочетание клавиш (Ctrl+…)", lambda: B("Сочетание", NONE, A.key(["ctrl", "c"], "tap"))),
    ("Кнопка → клавиша-залипание", lambda: B("Залипание", NONE, A.key(["shift"], "toggle"))),
    ("Передача коробки → клавиша", lambda: B("Передача → 1", NONE, A.key(["1"], "tap"))),
    None,
    ("Кнопка → ЛКМ", lambda: B("ЛКМ", NONE, A.mouse("left"))),
    ("Кнопка → ПКМ", lambda: B("ПКМ", NONE, A.mouse("right"))),
    ("Кнопка → СКМ (колесо)", lambda: B("СКМ", NONE, A.mouse("middle"))),
    ("Кнопка → боковая мыши X1 / X2", lambda: B("X1", NONE, A.mouse("x1"))),
    None,
    ("Кнопка → колесо вверх", lambda: B("Колесо вверх", NONE, A.wheel("up", 10))),
    ("Кнопка → колесо вниз", lambda: B("Колесо вниз", NONE, A.wheel("down", 10))),
    None,
    ("Геймпад: руль → левый стик", lambda: B("Руль → левый стик", S.axis(0, "full"), A.stick("left", "right"),
                                               deadzone=0.02)),
    ("Геймпад: руль → правый стик (камера)", lambda: B("Руль → правый стик", S.axis(0, "full"),
                                                        A.stick("right", "right"), deadzone=0.02)),
    ("Геймпад: педаль → курок RT", lambda: B("Газ → RT", NONE, A.trigger("rt"), deadzone=0.02)),
    ("Геймпад: педаль → курок LT", lambda: B("Тормоз → LT", NONE, A.trigger("lt"), deadzone=0.02)),
    ("Геймпад: кнопка → кнопка геймпада (A, B, X, Y, LB…)", lambda: B("Кнопка A", NONE, A.pad_button("a"))),
    ("Геймпад: кнопка → крестовина геймпада", lambda: B("Крестовина ↑", NONE, A.pad_button("dup"))),
    ("Геймпад: кнопка → стик вверх", lambda: B("Стик вверх", NONE, A.stick("right", "up"))),
    None,
    ("Кнопка → вкл/выкл маппинг", lambda: B("Вкл/выкл", NONE, A.toggle())),
    ("Пустая привязка", lambda: B("Новая привязка", NONE, A.key(["w"]))),
]
