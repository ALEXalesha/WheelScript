"""Где лежат настройки и как их читать/писать."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

from . import APP_NAME
from .model import Config, default_config

PORTABLE_FLAG = "portable.ini"
CONFIG_NAME = "config.json"


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(rel: str) -> Path:
    base = getattr(sys, "_MEIPASS", None)
    return (Path(base) if base else app_dir()) / rel


def is_portable() -> bool:
    return (app_dir() / PORTABLE_FLAG).exists()


def data_dir() -> Path:
    if is_portable():
        return app_dir() / "data"
    root = os.environ.get("APPDATA") or str(Path.home())
    return Path(root) / APP_NAME


def config_path() -> Path:
    return data_dir() / CONFIG_NAME


def load_config(path: Optional[Path] = None) -> tuple[Config, Optional[str]]:
    """Возвращает (конфиг, предупреждение). Битый файл не теряется — уходит в .bak."""
    path = path or config_path()
    if not path.exists():
        return default_config(), None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as e:
        backup = path.with_name(f"{path.stem}.broken-{time.strftime('%Y%m%d-%H%M%S')}.json")
        try:
            path.replace(backup)
            where = f"Старый файл сохранён как {backup.name}."
        except OSError:
            where = ""
        return default_config(), f"Не удалось прочитать настройки ({e.__class__.__name__}). " \
                                 f"Загружены настройки по умолчанию. {where}"
    return Config.from_dict(data), None


def save_config(cfg: Config, path: Optional[Path] = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def export_profile(profile, path: Path) -> None:
    path.write_text(json.dumps({"wheelscript_profile": 1, **profile.to_dict()},
                               ensure_ascii=False, indent=2), encoding="utf-8")


def import_profile(path: Path):
    from .model import Profile
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("bindings"), list):
        raise ValueError("Это не файл профиля WheelScript")
    return Profile.from_dict(data)
