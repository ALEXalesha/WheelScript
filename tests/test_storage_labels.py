"""Хранение настроек и подписи интерфейса."""

import json

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from wheelscript import labels, storage
from wheelscript.model import Config, default_config

from .strategies import DEV, DEV2, bindings, configs, json_values, junk_config

tmp_ok = settings(suppress_health_check=[HealthCheck.function_scoped_fixture])


@tmp_ok
@given(configs)
def test_save_load_roundtrip(tmp_path, cfg):
    path = tmp_path / "config.json"
    storage.save_config(cfg, path)
    loaded, warning = storage.load_config(path)
    assert warning is None and loaded == cfg
    assert not path.with_suffix(".tmp").exists()


@tmp_ok
@given(st.one_of(json_values, junk_config()))
def test_load_any_json(tmp_path, data):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    cfg, warning = storage.load_config(path)
    assert warning is None and cfg == Config.from_dict(data)


@tmp_ok
@given(st.binary(max_size=200))
def test_load_garbage_bytes(tmp_path, blob):
    path = tmp_path / "config.json"
    for old in tmp_path.glob("*.json"):
        old.unlink()
    path.write_bytes(blob)
    cfg, warning = storage.load_config(path)
    assert isinstance(cfg, Config)
    if warning:
        assert cfg == default_config()
        assert list(tmp_path.glob("config.broken-*.json")), "битый файл сохранён в .broken"


def test_deeply_nested_json(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("[" * 100000 + "]" * 100000, encoding="utf-8")
    cfg, warning = storage.load_config(path)
    assert cfg == default_config() and warning


def test_missing_file_gives_default(tmp_path):
    cfg, warning = storage.load_config(tmp_path / "nope.json")
    assert cfg == default_config() and warning is None


@given(bindings(), st.sampled_from([None, {}, {DEV: "Руль"}, {DEV: "Руль", DEV2: "Педали"}]))
def test_labels_never_crash(b, names):
    assert labels.source_text(b.source, names)
    assert labels.action_text(b.action)
    assert isinstance(labels.params_text(b), str)
