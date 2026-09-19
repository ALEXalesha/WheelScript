import os

from hypothesis import HealthCheck, settings

settings.register_profile("default", max_examples=300, deadline=None,
                          suppress_health_check=[HealthCheck.too_slow])
settings.register_profile("thorough", max_examples=5000, deadline=None,
                          suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))


# ---- Qt: ни один настоящий диалог не должен всплыть во время тестов ----
import pytest  # noqa: E402

_DIALOG_FUNCS = ("info", "warning", "error", "yes_no", "ask_text", "open_path", "save_path")


@pytest.fixture(autouse=True)
def no_real_dialogs(monkeypatch):
    try:
        from wheelscript.qt import dialogs
    except ImportError:  # без PySide6 тесты интерфейса пропускаются сами
        return

    def refuse(name):
        def call(*args, **kwargs):
            raise AssertionError(f"неожиданный диалог {name}{args[1:]}")
        return call

    for name in _DIALOG_FUNCS:
        monkeypatch.setattr(dialogs, name, refuse(name))
