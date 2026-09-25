"""Главное окно WheelScript."""

from __future__ import annotations

import logging
import os
import queue
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QItemSelectionModel, QModelIndex, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QHBoxLayout,
                               QHeaderView, QLabel, QMainWindow, QMenu, QPushButton, QSlider, QSpinBox,
                               QSplitter, QStyle, QStyledItemDelegate, QTableView, QToolButton, QVBoxLayout,
                               QWidget)

from .. import APP_NAME, __version__, keys, storage, theme
from ..engine import binding_value, shape
from ..model import (RUMBLE, TICK_RATE, Binding, Config, Profile, Settings, clean_text, default_profile,
                     gamepad_profile, unique_name)
from ..presets import PRESETS
from ..theme import P
from . import dialogs, window_geometry
from .binding_dialog import BindingDialog
from .bindings_model import ON_COLUMN, BindingsModel
from .fields import Choice, KeyField
from .monitor import Monitor

log = logging.getLogger(__name__)

POLL_MS = 40
PROFILE_FILTER = "Профиль WheelScript (*.json);;Все файлы (*.*)"
MAX_PROFILES = 64


class StatusDot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.color = P["off"]
        self.setFixedSize(16, 16)

    def set_color(self, color: str) -> None:
        if color != self.color:
            self.color = color
            self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.color))
        p.drawEllipse(2, 2, 12, 12)
        p.end()


class RowDelegate(QStyledItemDelegate):
    """Выделение строки: windows11 рисует его еле заметной полоской в каждой ячейке, а в
    тёмной теме оно ещё и сливается с голубой подсветкой срабатывающих привязок. Рисуем
    своё: заливка цветом акцента и одна полоска у левого края строки."""

    SELECT_ALPHA = 110

    def paint(self, painter, option, index):
        selected = bool(option.state & QStyle.State_Selected)
        opt = type(option)(option)
        opt.state &= ~(QStyle.State_Selected | QStyle.State_HasFocus)
        super().paint(painter, opt, index)
        if not selected:
            return
        tint = QColor(P["accent"])
        tint.setAlpha(self.SELECT_ALPHA)
        painter.fillRect(option.rect, tint)
        if index.column() == 0:
            r = option.rect
            h = max(8, r.height() // 2)
            painter.save()
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(P["accent"]))
            painter.drawRoundedRect(QRect(r.left() + 1, r.top() + (r.height() - h) // 2, 3, h), 1.5, 1.5)
            painter.restore()


class BindingsView(QTableView):
    """Таблица: щелчок по «Вкл» переключает, повторный щелчок по строке снимает выделение."""
    toggle_requested = Signal(int)
    edit_requested = Signal(int)
    delete_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._deselect_row: Optional[int] = None
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.verticalHeader().hide()
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setAlternatingRowColors(False)
        self.setItemDelegate(RowDelegate(self))

    def mousePressEvent(self, event):
        self._deselect_row = None
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        index = self.indexAt(event.position().toPoint())
        if not index.isValid():
            self.clearSelection()
            self.setCurrentIndex(QModelIndex())
            return
        if index.column() == ON_COLUMN:
            self.toggle_requested.emit(index.row())
            return
        if self.selectionModel().isRowSelected(index.row(), QModelIndex()):
            self._deselect_row = index.row()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        row, self._deselect_row = self._deselect_row, None
        if row is not None:
            index = self.indexAt(event.position().toPoint())
            if index.isValid() and index.row() == row:
                self.clearSelection()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self._deselect_row = None
        if event.button() != Qt.LeftButton:
            return
        index = self.indexAt(event.position().toPoint())
        if not index.isValid():
            return
        if index.column() == ON_COLUMN:
            self.toggle_requested.emit(index.row())  # второй быстрый щелчок — ещё одно переключение
            return
        self.edit_requested.emit(index.row())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            self.delete_requested.emit()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            row = self.selected_row()
            if row is not None:
                self.edit_requested.emit(row)
            return
        if event.key() == Qt.Key_Escape:
            self.clearSelection()
            return
        super().keyPressEvent(event)

    def selected_row(self) -> Optional[int]:
        rows = self.selectionModel().selectedRows()
        return rows[0].row() if rows else None


class MainWindow(QMainWindow):
    def __init__(self, service, cfg: Config, cfg_path: Path, warning: Optional[str] = None):
        super().__init__()
        self.service = service
        self.cfg = cfg
        self.cfg_path = cfg_path
        self._infos: list = []
        self._error: Optional[str] = None
        self._closing = False
        self._status_color = ""
        title = f"{APP_NAME} {__version__}" + ("  (portable)" if storage.is_portable() else "")
        self.setWindowTitle(title)
        self.setMinimumSize(900, 560)
        self.resize(1180, 700)
        # Окно открывается там и такого размера, где его закрыли (3.1.0). window.json лежит
        # рядом с config.json - в тестах и при съёмке скриншотов это временная папка.
        self._window_path = cfg_path.with_name(storage.WINDOW_NAME)
        window_geometry.restore(self, storage.load_window(self._window_path))
        self._apply_theme()
        self._build()
        self._refresh_profiles()
        self._refresh_table()

        service.set_toggle_key(cfg.settings.toggle_key)
        service.set_tick_rate(cfg.settings.tick_rate)
        service.set_rumble(cfg.settings.rumble / 100)
        service.set_profile(cfg.active)
        if cfg.settings.start_enabled:
            service.set_enabled(True)
        self._update_status()
        QApplication.instance().styleHints().colorSchemeChanged.connect(self._on_system_scheme)
        self.timer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        if warning:
            QTimer.singleShot(300, lambda: dialogs.warning(self, warning))

    # --- оформление ---

    def _apply_theme(self) -> None:
        theme.apply(QApplication.instance(), self.cfg.settings.theme)

    def _recolor(self) -> None:
        """Перерисовать то, что программа рисует сама, в цветах текущей палитры."""
        theme.sync(QApplication.instance())
        self.model.repaint_colors()
        self.monitor.repaint_colors()
        self._recolor_labels()
        self._status_color = ""
        self._update_status()

    def _on_system_scheme(self, *_args) -> None:
        self._recolor()

    def set_theme(self, mode: str) -> None:
        if mode != self.cfg.settings.theme:
            self._commit(Config(self._settings(theme=mode), self.cfg.profiles), push=False)
        self._apply_theme()
        self._recolor()

    # --- построение ---

    def _build(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 10, 12, 10)
        self.setCentralWidget(central)
        self.hints: list[QLabel] = []

        top = QHBoxLayout()
        self.dot = StatusDot()
        self.status = QLabel("")
        f = self.status.font()
        f.setPointSizeF(f.pointSizeF() + 2)
        f.setBold(True)
        self.status.setFont(f)
        self.run_btn = QPushButton("Включить")
        self.run_btn.clicked.connect(self._toggle_running)
        top.addWidget(self.dot)
        top.addWidget(self.status)
        top.addSpacing(12)
        top.addWidget(self.run_btn)
        top.addStretch(1)
        top.addWidget(QLabel("Горячая клавиша вкл/выкл:"))
        hk = self.cfg.settings.toggle_key
        self.hotkey = KeyField((hk,) if hk else (), combo=False, allow_empty=True)
        self.hotkey.setMinimumWidth(300)
        self.hotkey.value_changed.connect(self._set_hotkey)
        self.hotkey.capture_changed.connect(self._capture_hook)
        top.addWidget(self.hotkey)
        root.addLayout(top)

        prof = QHBoxLayout()
        prof.addWidget(QLabel("Профиль:"))
        self.profile_cb = QComboBox()
        self.profile_cb.setMinimumWidth(300)
        self.profile_cb.activated.connect(self._select_profile)
        prof.addWidget(self.profile_cb)
        self.profile_btn = QToolButton()
        self.profile_btn.setText("Действия с профилем")
        self.profile_btn.setPopupMode(QToolButton.InstantPopup)
        self.profile_menu = QMenu(self.profile_btn)
        for item in (("Новый пустой профиль…", self._profile_new),
                           ("Новый стандартный (PXN V9: руль как мышь)…", self._profile_new_default),
                           ("Новый: руль как геймпад Xbox…", self._profile_new_gamepad),
                           ("Копия текущего…", self._profile_copy),
                           ("Переименовать…", self._profile_rename),
                           ("Удалить", self._profile_delete), None,
                           ("Импорт из файла…", self._profile_import),
                     ("Экспорт в файл…", self._profile_export)):
            if item is None:
                self.profile_menu.addSeparator()
            else:
                text, slot = item
                self.profile_menu.addAction(text).triggered.connect(lambda _c=False, s=slot: s())
        self.profile_btn.setMenu(self.profile_menu)
        prof.addWidget(self.profile_btn)
        prof.addStretch(1)
        root.addLayout(prof)

        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        self.model = BindingsModel(self)
        self.table = BindingsView()
        self.table.setModel(self.model)
        # колонки делят ширину таблицы, как в 2.x: без горизонтальной прокрутки
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setSectionResizeMode(ON_COLUMN, QHeaderView.Fixed)
        self.table.setColumnWidth(ON_COLUMN, 48)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.toggle_requested.connect(self._toggle_binding)
        self.table.edit_requested.connect(self._edit_row)
        self.table.delete_requested.connect(self._delete)
        left_lay.addWidget(self.table, 1)

        bar = QHBoxLayout()
        self.add_btn = QToolButton()
        self.add_btn.setText("＋ Добавить")
        self.add_btn.setPopupMode(QToolButton.InstantPopup)
        self.add_menu = QMenu(self.add_btn)
        for preset in PRESETS:
            if preset is None:
                self.add_menu.addSeparator()
            else:
                label, factory = preset
                self.add_menu.addAction(label).triggered.connect(lambda _c=False, f=factory: self._add(f()))
        self.add_btn.setMenu(self.add_menu)
        bar.addWidget(self.add_btn)
        self.row_buttons = {}
        for key, text, slot in (("edit", "Изменить", self._edit), ("copy", "Копия", self._duplicate),
                                ("delete", "Удалить", self._delete), ("up", "▲", lambda: self._move(-1)),
                                ("down", "▼", lambda: self._move(1))):
            b = QPushButton(text)
            if len(text) == 1:
                b.setFixedWidth(36)
            b.clicked.connect(slot)
            bar.addWidget(b)
            self.row_buttons[key] = b
        bar.addStretch(1)
        hint = QLabel("Подсвечено голубым — то, что сейчас срабатывает")
        self.hints.append(hint)
        bar.addWidget(hint)
        left_lay.addLayout(bar)

        self.monitor = Monitor(self.cfg.settings.monitor_device)
        self.monitor.device_selected.connect(self._monitor_select)
        split.addWidget(left)
        split.addWidget(self.monitor)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([760, 380])
        root.addWidget(split, 1)

        bottom = QHBoxLayout()
        self.start_cb = QCheckBox("Включать маппинг сразу при запуске")
        self.start_cb.setChecked(self.cfg.settings.start_enabled)
        self.start_cb.toggled.connect(self._set_start_enabled)
        bottom.addWidget(self.start_cb)
        bottom.addSpacing(18)
        bottom.addWidget(QLabel("Частота опроса, Гц:"))
        self.tick_spin = QSpinBox()
        self.tick_spin.setRange(*TICK_RATE)
        self.tick_spin.setSingleStep(5)
        self.tick_spin.setValue(self.cfg.settings.tick_rate)
        self.tick_spin.editingFinished.connect(self._set_tick)
        self.tick_spin.valueChanged.connect(lambda _v: None if self.tick_spin.hasFocus() else self._set_tick())
        bottom.addWidget(self.tick_spin)
        bottom.addSpacing(18)
        bottom.addWidget(QLabel("Тема:"))
        self.theme_cb = Choice(theme.LABELS, self.cfg.settings.theme, self.set_theme)
        bottom.addWidget(self.theme_cb)
        self.error_lbl = QLabel("")
        bottom.addStretch(1)
        bottom.addWidget(self.error_lbl)
        self.shortcut_btn = QPushButton("Ярлык в «Пуск»")
        self.shortcut_btn.clicked.connect(self._make_shortcut)
        self.data_btn = QPushButton("Папка настроек")
        self.data_btn.clicked.connect(self._open_data_dir)
        bottom.addWidget(self.shortcut_btn)
        bottom.addWidget(self.data_btn)
        root.addLayout(bottom)

        pad_row = QHBoxLayout()
        self.pad_lbl = QLabel(f"Геймпад: {getattr(self.service, 'pad_status', 'не используется')}")
        self.hints.append(self.pad_lbl)
        pad_row.addWidget(self.pad_lbl)
        pad_row.addSpacing(18)
        pad_row.addWidget(QLabel("Вибрация из игры на руль:"))
        self.rumble_slider = QSlider(Qt.Horizontal)
        self.rumble_slider.setRange(*RUMBLE)
        self.rumble_slider.setFixedWidth(140)
        self.rumble_pct = QLabel(f"{self.cfg.settings.rumble}%")
        self.rumble_pct.setMinimumWidth(40)
        self.rumble_slider.setValue(self.cfg.settings.rumble)
        self.rumble_slider.valueChanged.connect(self._rumble_move)
        self.rumble_slider.sliderReleased.connect(self._set_rumble)
        self.rumble_slider.actionTriggered.connect(lambda _a: QTimer.singleShot(0, self._rumble_keyboard))
        pad_row.addWidget(self.rumble_slider)
        pad_row.addWidget(self.rumble_pct)
        self.rumble_test_btn = QPushButton("Проверить")
        self.rumble_test_btn.clicked.connect(self.service.rumble_test)
        pad_row.addWidget(self.rumble_test_btn)
        self.rumble_lbl = QLabel(getattr(self.service, "rumble_status", ""))
        self.hints.append(self.rumble_lbl)
        pad_row.addWidget(self.rumble_lbl)
        pad_row.addStretch(1)
        root.addLayout(pad_row)
        self._recolor_labels()

        self.table.selectionModel().selectionChanged.connect(lambda *_a: self._update_row_buttons())
        self._update_row_buttons()

    def _recolor_labels(self) -> None:
        self.error_lbl.setStyleSheet(f"color: {P['error']};")
        for lbl in self.hints:
            lbl.setStyleSheet(f"color: {P['off']};")

    # --- конфиг ---

    @property
    def profile(self) -> Profile:
        return self.cfg.active

    def _commit(self, cfg: Config, push: bool = True) -> None:
        self.cfg = Config.from_dict(cfg.to_dict())
        try:
            storage.save_config(self.cfg, self.cfg_path)
        except OSError as e:
            dialogs.error(self, f"Не удалось сохранить настройки:\n{e}")
        if push:
            self.service.set_profile(self.cfg.active)
        self._refresh_profiles()
        self._refresh_table()

    def _settings(self, **kw) -> Settings:
        return Settings.from_dict(self.cfg.settings.to_dict() | kw)

    def _set_bindings(self, bindings: list[Binding], select: Optional[int] = None) -> None:
        active = self.cfg.settings.active_profile
        profile = Profile(self.profile.name, tuple(bindings))
        profiles = tuple(profile if p.name == active else p for p in self.cfg.profiles)
        self._commit(Config(self.cfg.settings, profiles))
        self.select(select)

    # --- таблица ---

    def _refresh_table(self) -> None:
        sel = self.selected_row()
        self.model.set_bindings(self.profile.bindings, self.service.device_names())
        self.select(sel)

    def selected_row(self) -> Optional[int]:
        return self.table.selected_row() if hasattr(self, "table") else None

    def select(self, row: Optional[int]) -> None:
        if row is None or not 0 <= row < self.model.rowCount():
            self.table.clearSelection()
            self._update_row_buttons()
            return
        index = self.model.index(row, 1)
        self.table.selectionModel().setCurrentIndex(
            index, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
        self.table.scrollTo(index)
        self._update_row_buttons()

    def _update_row_buttons(self) -> None:
        row = self.selected_row()
        has = row is not None
        for key in ("edit", "copy", "delete"):
            self.row_buttons[key].setEnabled(has)
        self.row_buttons["up"].setEnabled(has and row > 0)
        self.row_buttons["down"].setEnabled(has and row < self.model.rowCount() - 1)

    def _toggle_binding(self, row: int) -> None:
        bindings = list(self.profile.bindings)
        if not 0 <= row < len(bindings):
            return
        b = bindings[row]
        bindings[row] = Binding.from_dict(b.to_dict() | {"enabled": not b.enabled})
        self._set_bindings(bindings, row)

    def open_dialog(self, binding: Binding, title: str) -> Optional[Binding]:
        dlg = BindingDialog(self, self.service, binding, title)
        dlg.exec()
        result = dlg.result_binding
        dlg.deleteLater()
        return result

    def _add(self, binding: Binding) -> None:
        result = self.open_dialog(binding, "Новая привязка")
        if result:
            bindings = list(self.profile.bindings) + [result]
            self._set_bindings(bindings, len(bindings) - 1)

    def _edit_row(self, row: int) -> None:
        if not 0 <= row < len(self.profile.bindings):
            return
        self.select(row)
        result = self.open_dialog(self.profile.bindings[row], "Изменить привязку")
        if result:
            bindings = list(self.profile.bindings)
            bindings[row] = result
            self._set_bindings(bindings, row)

    def _edit(self) -> None:
        row = self.selected_row()
        if row is not None:
            self._edit_row(row)

    def _duplicate(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        bindings = list(self.profile.bindings)
        b = bindings[row]
        bindings.insert(row + 1, Binding.from_dict(b.to_dict() | {"name": f"{b.name} (копия)"}))
        self._set_bindings(bindings, row + 1)

    def _delete(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        b = self.profile.bindings[row]
        if not dialogs.yes_no(self, f"Удалить привязку «{b.name}»?"):
            return
        bindings = list(self.profile.bindings)
        del bindings[row]
        self._set_bindings(bindings, min(row, len(bindings) - 1) if bindings else None)

    def _move(self, delta: int) -> None:
        row = self.selected_row()
        if row is None:
            return
        j = row + delta
        bindings = list(self.profile.bindings)
        if not 0 <= j < len(bindings):
            return
        bindings[row], bindings[j] = bindings[j], bindings[row]
        self._set_bindings(bindings, j)

    # --- профили ---

    def _refresh_profiles(self) -> None:
        names = [p.name for p in self.cfg.profiles]
        self.profile_cb.blockSignals(True)
        self.profile_cb.clear()
        self.profile_cb.addItems(names)
        self.profile_cb.setCurrentIndex(names.index(self.profile.name))
        self.profile_cb.blockSignals(False)

    def _taken(self, exclude: str = "") -> set[str]:
        return {p.name for p in self.cfg.profiles if p.name != exclude}

    def _ask_name(self, prompt: str, initial: str, exclude: str = "") -> Optional[str]:
        raw = dialogs.ask_text(self, prompt, initial)
        if raw is None:
            return None
        name = clean_text(raw, "")
        if not name:
            dialogs.error(self, "Имя не может быть пустым.")
            return None
        if name in self._taken(exclude):
            dialogs.error(self, f"Профиль «{name}» уже есть.")
            return None
        return name

    def _add_profile(self, profile: Profile) -> None:
        if len(self.cfg.profiles) >= MAX_PROFILES:
            dialogs.error(self, "Слишком много профилей (максимум 64).")
            return
        self._commit(Config(self._settings(active_profile=profile.name), self.cfg.profiles + (profile,)))

    def _select_profile(self, index: int) -> None:
        names = [p.name for p in self.cfg.profiles]
        if 0 <= index < len(names) and names[index] != self.cfg.settings.active_profile:
            self._commit(Config(self._settings(active_profile=names[index]), self.cfg.profiles))

    def _profile_new(self) -> None:
        name = self._ask_name("Имя нового профиля:", unique_name("Новый профиль", self._taken()))
        if name:
            self._add_profile(Profile(name, ()))

    def _profile_new_default(self) -> None:
        base = default_profile()
        name = self._ask_name("Имя нового профиля:", unique_name(base.name, self._taken()))
        if name:
            self._add_profile(Profile(name, base.bindings))

    def _profile_new_gamepad(self) -> None:
        base = gamepad_profile()
        name = self._ask_name("Имя нового профиля:", unique_name(base.name, self._taken()))
        if name:
            self._add_profile(Profile(name, base.bindings))

    def _profile_copy(self) -> None:
        name = self._ask_name("Имя копии:", unique_name(f"{self.profile.name} (копия)", self._taken()))
        if name:
            self._add_profile(Profile(name, self.profile.bindings))

    def _profile_rename(self) -> None:
        old = self.profile.name
        name = self._ask_name("Новое имя профиля:", old, exclude=old)
        if not name or name == old:
            return
        profiles = tuple(Profile(name, p.bindings) if p.name == old else p for p in self.cfg.profiles)
        self._commit(Config(self._settings(active_profile=name), profiles), push=False)

    def _profile_delete(self) -> None:
        if len(self.cfg.profiles) <= 1:
            dialogs.info(self, "Это единственный профиль — его нельзя удалить.")
            return
        old = self.profile.name
        if not dialogs.yes_no(self, f"Удалить профиль «{old}»?"):
            return
        profiles = tuple(p for p in self.cfg.profiles if p.name != old)
        self._commit(Config(self._settings(active_profile=profiles[0].name), profiles))

    def _profile_import(self) -> None:
        path = dialogs.open_path(self, "Импорт профиля", PROFILE_FILTER)
        if not path:
            return
        try:
            prof = storage.import_profile(Path(path))
        except (OSError, ValueError, UnicodeDecodeError, RecursionError) as e:
            dialogs.error(self, f"Не удалось импортировать:\n{e}")
            return
        self._add_profile(Profile(unique_name(prof.name, self._taken()), prof.bindings))

    def _profile_export(self) -> None:
        path = dialogs.save_path(self, "Экспорт профиля", f"{self.profile.name}.json", PROFILE_FILTER)
        if not path:
            return
        try:
            storage.export_profile(self.profile, Path(path))
        except OSError as e:
            dialogs.error(self, f"Не удалось сохранить:\n{e}")

    # --- настройки ---

    def _toggle_running(self) -> None:
        self.service.toggle()
        self._update_status()

    def _capture_hook(self, active: bool) -> None:
        # пока ловим клавишу, горячая клавиша не должна переключать маппинг
        if active:
            self.service.suspend()
        else:
            self.service.resume()

    def _set_hotkey(self, value: tuple) -> None:
        name = value[-1] if value else ""
        self.service.set_toggle_key(name)
        self._commit(Config(self._settings(toggle_key=name), self.cfg.profiles), push=False)
        self._update_status()

    def _set_start_enabled(self, checked: bool) -> None:
        self._commit(Config(self._settings(start_enabled=bool(checked)), self.cfg.profiles), push=False)

    def _set_tick(self) -> None:
        hz = max(TICK_RATE[0], min(TICK_RATE[1], self.tick_spin.value()))
        if hz != self.cfg.settings.tick_rate:
            self.service.set_tick_rate(hz)
            self._commit(Config(self._settings(tick_rate=hz), self.cfg.profiles), push=False)

    def _rumble_move(self, value: int) -> None:
        self.rumble_pct.setText(f"{value}%")
        self.service.set_rumble(value / 100)

    def _rumble_keyboard(self) -> None:
        if not self.rumble_slider.isSliderDown():
            self._set_rumble()

    def _set_rumble(self) -> None:
        pct = max(RUMBLE[0], min(RUMBLE[1], self.rumble_slider.value()))
        self._rumble_move(pct)
        if pct != self.cfg.settings.rumble:
            self._commit(Config(self._settings(rumble=pct), self.cfg.profiles), push=False)

    def _monitor_select(self, key: str) -> None:
        self._commit(Config(self._settings(monitor_device=key), self.cfg.profiles), push=False)

    def _make_shortcut(self) -> None:
        from .. import shortcut
        try:
            path = shortcut.create()
        except Exception as e:  # noqa: BLE001
            log.exception("shortcut failed")
            dialogs.error(self, f"Не удалось создать ярлык:\n{e}")
            return
        dialogs.info(self, f"Ярлык создан в меню «Пуск»:\n{path}\n\n"
                           f"Теперь {APP_NAME} находится через поиск Windows.")

    def _open_data_dir(self) -> None:
        d = self.cfg_path.parent
        d.mkdir(parents=True, exist_ok=True)
        os.startfile(d)  # noqa: S606  (только Windows)

    # --- цикл обновления ---

    def poll(self) -> None:
        if self._closing:
            return
        try:
            while True:
                ev = self.service.events.get_nowait()
                if ev[0] == "devices":
                    self._refresh_table()
                elif ev[0] == "pad_status":
                    self.pad_lbl.setText(f"Геймпад: {ev[1]}")
                elif ev[0] == "rumble_status":
                    self.rumble_lbl.setText(ev[1])
                elif ev[0] == "error":
                    self._error = ev[1]
                    self.error_lbl.setText(f"Ошибка: {ev[1]}"[:120])
        except queue.Empty:
            pass
        try:
            states, infos = self.service.snapshot()
            self._infos = infos
            self.monitor.update_view(states, infos)
            self.update_live(states, infos)
            self._update_status()
        except Exception:  # noqa: BLE001
            log.exception("ui poll failed")

    def update_live(self, states, infos) -> list[int]:
        default = infos[0].key if infos else None
        live = []
        for b in self.profile.bindings:
            v = binding_value(b, states, default) if b.enabled else None
            if v is None:
                live.append(False)
            elif b.action.is_analog:
                live.append(shape(abs(v), b.deadzone, b.curve) > 0)
            else:
                live.append(abs(v) >= b.threshold)
        return self.model.set_live(live)

    def _update_status(self) -> None:
        hk = self.cfg.settings.toggle_key
        suffix = f" ({keys.display(hk)})" if hk else ""
        if not self._infos:
            text, color = "Руль не найден", P["off"]
        elif self.service.enabled:
            text, color = "Маппинг ВКЛЮЧЁН", P["on"]
        else:
            text, color = "Маппинг выключен", P["off"]
        if self.status.text() != text:
            self.status.setText(text)
        if self._status_color != color:
            self._status_color = color
            self.status.setStyleSheet(f"color: {color};")
        self.dot.set_color(color)
        label = ("Выключить" if self.service.enabled else "Включить") + suffix
        if self.run_btn.text() != label:
            self.run_btn.setText(label)

    def closeEvent(self, event):
        self._closing = True
        storage.save_window(window_geometry.encode(self), self._window_path)
        self.timer.stop()
        try:
            self.service.stop()
        finally:
            event.accept()
