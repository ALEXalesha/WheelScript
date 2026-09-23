import sys

import pytest

from wheelscript import shortcut


@pytest.mark.skipif(sys.platform != "win32", reason="ярлыки .lnk только в Windows")
def test_create_shortcut_in_weird_path(tmp_path):
    """Кавычки, $, кириллица и буквы не из кодовой страницы системы не ломают ярлык.

    Ярлык пишется через IShellLinkW, без Windows Script Host, поэтому пропускать
    проверку на машинах с выключенным WSH больше не нужно.
    """
    # Японские буквы - потому что их нет ни в одной кодировке русской Windows: так
    # проверка ловит здесь то же, что раннер GitHub (английская Windows) ловил на
    # кириллице. WScript.Shell сохранял ярлык через ANSI и падал на «????».
    target = tmp_path / "Пуск 開始 $(echo x) 'q'" / "WheelScript.lnk"
    path = shortcut.create(target)
    assert path.exists() and path.stat().st_size > 0


@pytest.mark.skipif(sys.platform != "win32", reason="ярлыки .lnk только в Windows")
def test_a_failed_shortcut_says_why(tmp_path, monkeypatch):
    """Неудача обязана объясниться. Раньше сюда прилетал голый CalledProcessError:
    текст ошибки PowerShell ловился в stderr и молча выбрасывался, а окно
    показывало человеку строку, из которой нельзя понять ровно ничего.
    """
    monkeypatch.setattr(shortcut, "_PS", "Write-Error 'сломано нарочно 壊れた'; exit 1")
    with pytest.raises(OSError) as beda:
        shortcut.create(tmp_path / "нет.lnk")
    assert "сломано нарочно 壊れた" in str(beda.value)
