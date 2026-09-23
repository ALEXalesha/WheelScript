"""Ярлык в меню «Пуск» — по нему WheelScript находится через поиск Windows."""

from __future__ import annotations

import base64
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
#
# Ярлык пишется через IShellLinkW + IPersistFile, а не через WScript.Shell: тот
# сохраняет .lnk через ANSI и на буквах не из кодовой страницы системы (кириллица на
# английской Windows, иероглифы на русской) падал с «Unable to save shortcut ????».
# Нашлось на раннере GitHub, где Windows английская.
_PS = r"""
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;

[ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("000214F9-0000-0000-C000-000000000046")]
interface IShellLinkW {
    void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder file, int cch, IntPtr fd, int flags);
    void GetIDList(out IntPtr pidl);
    void SetIDList(IntPtr pidl);
    void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder name, int cch);
    void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string name);
    void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder dir, int cch);
    void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string dir);
    void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder args, int cch);
    void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string args);
    void GetHotkey(out short hotkey);
    void SetHotkey(short hotkey);
    void GetShowCmd(out int cmd);
    void SetShowCmd(int cmd);
    void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder path, int cch, out int index);
    void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string path, int index);
    void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string rel, int reserved);
    void Resolve(IntPtr hwnd, int flags);
    void SetPath([MarshalAs(UnmanagedType.LPWStr)] string file);
}

[ComImport, Guid("00021401-0000-0000-C000-000000000046")]
class ShellLink {}

public static class WheelScriptLink {
    public static void Save(string lnk, string target, string args, string dir, string icon, string desc) {
        var link = (IShellLinkW)new ShellLink();
        link.SetPath(target);
        link.SetArguments(args);
        link.SetWorkingDirectory(dir);
        link.SetIconLocation(icon, 0);
        link.SetDescription(desc);
        ((IPersistFile)link).Save(lnk, true);
    }
}
'@
[WheelScriptLink]::Save($env:WS_LNK, $env:WS_TARGET, $env:WS_ARGS, $env:WS_DIR, $env:WS_ICON, $env:WS_DESC)
"""

# Без этого PowerShell пишет stderr в OEM-кодировке, и буквы, которых в ней нет,
# теряются ещё до Python: причина ошибки доходила до человека вопросительными знаками.
_UTF8 = "$ErrorActionPreference='Stop';[Console]::OutputEncoding=[Text.Encoding]::UTF8;"


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


def _console_text(raw: bytes) -> str:
    """Windows PowerShell пишет stderr в кодировке консоли, а не в UTF-8.

    На русской Windows это cp866, и русское сообщение об ошибке, прочитанное как
    UTF-8, превращается в кашу - то есть причина, ради которой stderr и ловится,
    до человека не доходит.
    """
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    if sys.platform == "win32":
        try:
            import ctypes
            return raw.decode(f"cp{ctypes.windll.kernel32.GetOEMCP()}")
        except (LookupError, UnicodeDecodeError, OSError, AttributeError):
            pass
    return raw.decode("utf-8", "replace")


def create(path: Optional[Path] = None) -> Path:
    path = path or shortcut_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    exe, args, workdir, icon = _target()
    env = os.environ | {"WS_LNK": str(path), "WS_TARGET": exe, "WS_ARGS": args, "WS_DIR": workdir,
                        "WS_ICON": icon, "WS_DESC": DESCRIPTION}
    # check=True дал бы голый CalledProcessError без единого слова о причине: сам
    # текст ошибки PowerShell при этом уже пойман в stderr и молча выброшен. А
    # причина бывает внешняя - права на папку, политика, запрещающая PowerShell, -
    # и человеку в окне показывают именно её.
    # -EncodedCommand: текст скрипта идёт в UTF-16, и кодовая страница его не портит.
    encoded = base64.b64encode((_UTF8 + _PS).encode("utf-16-le")).decode("ascii")
    done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                          env=env, capture_output=True, timeout=60, creationflags=CREATE_NO_WINDOW)
    if done.returncode or not path.exists():
        why = _console_text(done.stderr or b"").strip() or f"код {done.returncode}"
        raise OSError(f"ярлык не создан: {path}\n{why}")
    return path
