"""Находки проверки 23.10 (Claude, установленная 3.2.0, этап 7 задания 07): стрелка меню у кнопок «Добавить»
и «Действия с профилем», ширина колонок по содержимому, длинные тире, бледный статус геймпада."""

from pathlib import Path

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from wheelscript.layout import fit_widths
from wheelscript.model import Binding
from wheelscript.qt.bindings_model import ON_COLUMN

from .test_gui import svc, win  # noqa: F401  (фикстуры окна)

ROOT = Path(__file__).resolve().parents[1]


@given(st.lists(st.integers(0, 900), min_size=1, max_size=8), st.integers(0, 3000))
@example([109, 119, 25, 66, 94, 100], 547)   # CI 25.10: остаток округления делал самую широкую шире текста
def test_ширины_колонок_в_сумме_ровно_доступное_и_по_содержимому_когда_влезает(needs, available):
    w = fit_widths(needs, available, minimum=60)
    assert len(w) == len(needs)
    assert sum(w) == available
    want = [max(60, n) for n in needs]
    if sum(want) <= available:
        assert all(a >= b for a, b in zip(w, want)), "влезает - каждая не уже своего текста"
    elif available >= 60 * len(needs):
        assert all(a >= 60 for a in w), "не влезает - но не уже минимума"
        assert all(a <= b for a, b in zip(w, want)), "и не шире своего текста"


def test_пустой_список_колонок():
    assert fit_widths([], 500) == []


def test_название_не_обрезается_а_параметры_не_забирают_лишнее(win, qapp):
    long_name = "Камера вверх (крестовина, удержание)"
    b0 = win.profile.bindings[0]
    win.model.set_bindings([Binding.make(long_name, b0.source, b0.action)] + list(win.profile.bindings[1:]),
                           win.service.device_names())
    win.resize(1200, 700)
    QApplication.processEvents()
    win.table.fit_columns()
    t = win.table
    name_col = 1
    cols = [c for c in range(win.model.columnCount()) if c != ON_COLUMN]
    need = {c: max(t.horizontalHeader().sectionSizeHint(c), t.sizeHintForColumn(c)) + t.PAD for c in cols}
    if t.columnWidth(name_col) < need[name_col]:
        # не влезает всё - тогда ни одна колонка не держит места больше своего текста («Параметры» с запасом)
        assert all(t.columnWidth(c) <= need[c] for c in cols), {c: (t.columnWidth(c), need[c]) for c in cols}
    # и «Название» не уже, чем при прежнем делении поровну
    assert t.columnWidth(name_col) >= (t.viewport().width() - t.ON_WIDTH) // len(cols)
    total = sum(t.columnWidth(c) for c in range(win.model.columnCount()))
    assert total == t.viewport().width(), "колонки ровно по ширине таблицы, без прокрутки"
    assert t.columnWidth(ON_COLUMN) == t.ON_WIDTH


def test_кнопки_с_меню_со_своей_стрелкой_без_индикатора_fusion(win):
    for btn in (win.add_btn, win.profile_btn):
        assert btn.text().endswith("▾"), btn.text()
        assert "menu-indicator" in btn.styleSheet() and "image: none" in btn.styleSheet()
        assert btn.menu() is not None


def test_состояние_геймпада_и_вибрации_обычным_цветом_а_не_бледным(win):
    for lbl in (win.pad_lbl, win.rumble_lbl):
        assert lbl not in win.hints
        assert "color" not in lbl.styleSheet(), "цвет текста из палитры, как у остального окна"


def test_в_текстах_программы_нет_длинного_тире():
    bad = [f"{p.relative_to(ROOT)}:{i}" for p in sorted((ROOT / "wheelscript").rglob("*.py"))
           for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if "—" in line]
    for doc in ("README.md", "README.ru.md", "CHANGELOG.md"):
        bad += [f"{doc}:{i}" for i, line in enumerate((ROOT / doc).read_text(encoding="utf-8").splitlines(), 1)
                if "—" in line]
    assert bad == []
