import json

import pytest

from pop_translate import config as config_module
from pop_translate.config import Config


def load_config(tmp_path, monkeypatch, data):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data))
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(path))
    monkeypatch.delenv("POP_TRANSLATE_MODEL", raising=False)
    monkeypatch.delenv("POP_TRANSLATE_VISION_MODEL", raising=False)
    config = Config()
    config.load()
    return config


def test_default_text_and_vision_models_use_deepseek_flash():
    config = Config()
    assert config.model == config.vision_model == "deepseek-flash"


@pytest.mark.parametrize("legacy", ["deepseek-chat", "deepseek-reasoner", "deepseek-v4-flash"])
def test_saved_legacy_text_models_migrate(tmp_path, monkeypatch, legacy):
    config = load_config(tmp_path, monkeypatch, {"model": legacy})
    assert config.model == "deepseek-flash"


def test_saved_legacy_vision_model_migrates(tmp_path, monkeypatch):
    config = load_config(tmp_path, monkeypatch, {"vision_model": "deepseek-v4-flash-vision-exp"})
    assert config.vision_model == "deepseek-flash"


def test_custom_models_are_preserved(tmp_path, monkeypatch):
    config = load_config(tmp_path, monkeypatch, {"model": "custom-text", "vision_model": "custom-vision"})
    assert config.model == "custom-text"
    assert config.vision_model == "custom-vision"


def test_environment_models_still_take_precedence(tmp_path, monkeypatch):
    load_config(tmp_path, monkeypatch, {"model": "deepseek-v4-flash", "vision_model": "deepseek-v4-flash-vision-exp"})
    monkeypatch.setenv("POP_TRANSLATE_MODEL", "provider-text")
    monkeypatch.setenv("POP_TRANSLATE_VISION_MODEL", "provider-vision")
    config = Config()
    config.load()
    assert config.model == "provider-text"
    assert config.vision_model == "provider-vision"
