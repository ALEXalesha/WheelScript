"""Таблица привязок активного профиля."""

from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor

from .. import labels
from ..model import Binding
from ..theme import P

COLUMNS = ("Вкл", "Название", "Ввод с руля", "Действие", "Параметры")
ON_COLUMN = 0


class BindingsModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bindings: tuple[Binding, ...] = ()
        self._names: dict[str, str] = {}
        self._live: list[bool] = []

    @property
    def bindings(self) -> tuple[Binding, ...]:
        return self._bindings

    def set_bindings(self, bindings: Sequence[Binding], device_names: dict[str, str]) -> None:
        self.beginResetModel()
        self._bindings = tuple(bindings)
        self._names = dict(device_names)
        self._live = [False] * len(self._bindings)
        self.endResetModel()

    def set_live(self, live: Sequence[bool]) -> list[int]:
        """Подсветить срабатывающие строки. Возвращает номера строк, которые поменялись."""
        changed = [i for i, v in enumerate(live) if i < len(self._live) and self._live[i] != v]
        for i in changed:
            self._live[i] = live[i]
            self.dataChanged.emit(self.index(i, 0), self.index(i, len(COLUMNS) - 1), [Qt.BackgroundRole])
        return changed

    def is_live(self, row: int) -> bool:
        return 0 <= row < len(self._live) and self._live[row]

    def repaint_colors(self) -> None:
        if self._bindings:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self._bindings) - 1, len(COLUMNS) - 1),
                                  [Qt.BackgroundRole, Qt.ForegroundRole])

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._bindings)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole and 0 <= section < len(COLUMNS):
            return COLUMNS[section]
        return None

    def cell_text(self, row: int, col: int) -> str:
        b = self._bindings[row]
        if col == 0:
            return "✔" if b.enabled else "—"
        if col == 1:
            return b.name
        if col == 2:
            return labels.source_text(b.source, self._names)
        if col == 3:
            return labels.action_text(b.action)
        return labels.params_text(b)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._bindings):
            return None
        row, col = index.row(), index.column()
        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            return self.cell_text(row, col)
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignCenter) if col == ON_COLUMN else int(Qt.AlignVCenter | Qt.AlignLeft)
        if role == Qt.ForegroundRole and not self._bindings[row].enabled:
            return QBrush(QColor(P["disabled"]))
        if role == Qt.BackgroundRole and self._live[row]:
            return QBrush(QColor(P["live_bg"]))
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable
