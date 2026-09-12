"""Ярлык в меню «Пуск» — по нему WheelScript находится через поиск Windows."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from . import APP_NAME, storage

CREATE_NO_WINDOW = 0x08000000
DESCRIPTION = "Руль как мышь и клавиатура"

# Пути передаются через переменные окружения, а не подставляются в текст команды:
# так кавычки и спецсимволы в пути к папке не сломают (и не «выполнят») скрипт.
_PS = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:WS_LNK);"
       "$s.TargetPath=$env:WS_TARGET;$s.Arguments=$env:WS_ARGS;$s.WorkingDirectory=$env:WS_DIR;"
       "$s.IconLocation=$env:WS_ICON;$s.Description=$env:WS_DESC;$s.Save()")


def start_menu_dir() -> Path:
    return Path(os.environ.get("APPDATA") or Path.home()) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def shortcut_path() -> Path:
    return start_menu_dir() / f"{APP_NAME}.lnk"


def _target() -> tuple[str, str, str, str]:
    if getattr(sys, "frozen", False):
        exe = sys.executable
        return exe, "", str(Path(exe).parent), exe
    pyw = Path(sys.executable).with_name("pythonw.exe")
    exe = str(pyw if pyw.exists() else Path(sys.executable))
    root = storage.app_dir()
    return exe, f'"{root / "run.py"}"', str(root), str(storage.resource_path("assets/icon.ico"))


def create(path: Optional[Path] = None) -> Path:
    path = path or shortcut_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    exe, args, workdir, icon = _target()
    env = os.environ | {"WS_LNK": str(path), "WS_TARGET": exe, "WS_ARGS": args, "WS_DIR": workdir,
                        "WS_ICON": icon, "WS_DESC": DESCRIPTION}
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS], env=env, check=True,
                   capture_output=True, timeout=30, creationflags=CREATE_NO_WINDOW)
    if not path.exists():
        raise OSError(f"ярлык не создан: {path}")
    return path
