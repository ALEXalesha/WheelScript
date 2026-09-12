import sys

import pytest

from wheelscript import shortcut


@pytest.mark.skipif(sys.platform != "win32", reason="ярлыки .lnk только в Windows")
def test_create_shortcut_in_weird_path(tmp_path):
    """Кавычки, $ и кириллица в пути не ломают создание ярлыка."""
    target = tmp_path / "Пуск $(echo x) 'q'" / "WheelScript.lnk"
    path = shortcut.create(target)
    assert path.exists() and path.stat().st_size > 0
