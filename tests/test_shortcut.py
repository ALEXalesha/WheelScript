import sys

import pytest

from wheelscript import shortcut


@pytest.mark.skipif(sys.platform != "win32", reason="ярлыки .lnk только в Windows")
def test_create_shortcut_in_weird_path(tmp_path):
    """Кавычки, $ и кириллица в пути не ломают создание ярлыка.

    Ярлык делает Windows Script Host через COM, а он бывает выключен политикой -
    на раннерах GitHub, например. Это не поломка программы, поэтому проверка в
    таком случае пропускается, но пропускается по названной причине: текст ошибки
    из PowerShell обязан дойти сюда, иначе отличить выключенный WSH от настоящей
    поломки было бы нечем.
    """
    target = tmp_path / "Пуск $(echo x) 'q'" / "WheelScript.lnk"
    try:
        path = shortcut.create(target)
    except OSError as err:
        if "WScript.Shell" in str(err) or "80040154" in str(err):
            pytest.skip(f"Windows Script Host недоступен: {err}")
        raise
    assert path.exists() and path.stat().st_size > 0


@pytest.mark.skipif(sys.platform != "win32", reason="ярлыки .lnk только в Windows")
def test_a_failed_shortcut_says_why(tmp_path, monkeypatch):
    """Неудача обязана объясниться. Раньше сюда прилетал голый CalledProcessError:
    текст ошибки PowerShell ловился в stderr и молча выбрасывался, а окно
    показывало человеку строку, из которой нельзя понять ровно ничего.
    """
    monkeypatch.setattr(shortcut, "_PS", "Write-Error 'сломано нарочно'; exit 1")
    with pytest.raises(OSError) as beda:
        shortcut.create(tmp_path / "нет.lnk")
    assert "сломано нарочно" in str(beda.value)
