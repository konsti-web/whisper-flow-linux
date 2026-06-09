# -*- coding: utf-8 -*-
"""Tests fuer Konfiguration und Migration."""

import json

from whisperflow.config import DEFAULT_CONFIG, Config


def test_defaults_without_file(tmp_path):
    cfg = Config(config_file=tmp_path / "config.json")
    assert cfg.get("backend") == "auto"
    assert cfg.get("model_size") == "auto"
    assert cfg.get("mode") == "live"
    assert cfg.get("typing_wpm") == 40
    assert cfg.get("dictionary_learn_threshold") == 3


def test_file_overrides_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"model_size": "small", "typing_wpm": 60}), encoding="utf-8")
    cfg = Config(config_file=path)
    assert cfg.get("model_size") == "small"
    assert cfg.get("typing_wpm") == 60
    assert cfg.get("backend") == "auto"  # Default bleibt


def test_migration_trigger_key(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"trigger_key": "ctrl"}), encoding="utf-8")
    cfg = Config(config_file=path)
    assert cfg.get("trigger_keys") == ["key:ctrl_l", "key:ctrl_r"]
    assert "trigger_key" not in cfg.config
    # Migration wurde persistiert
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert "trigger_key" not in saved
    assert saved["trigger_keys"] == ["key:ctrl_l", "key:ctrl_r"]


def test_migration_unknown_trigger_key_falls_back(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"trigger_key": "exotisch"}), encoding="utf-8")
    cfg = Config(config_file=path)
    assert cfg.get("trigger_keys") == DEFAULT_CONFIG["trigger_keys"]


def test_save_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    cfg = Config(config_file=path)
    cfg.set("model_size", "medium")
    cfg.update({"language": "de", "mode": "batch"})

    cfg2 = Config(config_file=path)
    assert cfg2.get("model_size") == "medium"
    assert cfg2.get("language") == "de"
    assert cfg2.get("mode") == "batch"


def test_none_value_with_nonnull_default_returns_default(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"hold_threshold": None}), encoding="utf-8")
    cfg = Config(config_file=path)
    assert cfg.get("hold_threshold") == DEFAULT_CONFIG["hold_threshold"]


def test_unknown_keys_preserved(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"custom_key": 123}), encoding="utf-8")
    cfg = Config(config_file=path)
    cfg.set("language", "en")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["custom_key"] == 123
