"""Все вопросы и сообщения пользователю в одном месте: тесты подменяют эти функции."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from .. import APP_NAME


def info(parent, text: str) -> None:
    QMessageBox.information(parent, APP_NAME, text)


def warning(parent, text: str) -> None:
    QMessageBox.warning(parent, APP_NAME, text)


def error(parent, text: str) -> None:
    QMessageBox.critical(parent, APP_NAME, text)


def yes_no(parent, text: str) -> bool:
    return QMessageBox.question(parent, APP_NAME, text) == QMessageBox.Yes


def ask_text(parent, prompt: str, initial: str) -> Optional[str]:
    text, ok = QInputDialog.getText(parent, APP_NAME, prompt, text=initial)
    return text if ok else None


def open_path(parent, title: str, file_filter: str) -> str:
    return QFileDialog.getOpenFileName(parent, title, "", file_filter)[0]


def save_path(parent, title: str, suggested: str, file_filter: str) -> str:
    path = QFileDialog.getSaveFileName(parent, title, suggested, file_filter)[0]
    if path and not path.lower().endswith(".json"):
        path += ".json"
    return path
