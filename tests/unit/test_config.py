import os
import yaml
import pytest
from unittest.mock import patch, mock_open
from src.infrastructure.config import AppConfig


def test_load_defaults():
    config = AppConfig.load(config_path="nonexistent_file.yaml")
    assert config.device_name == "Apple iPhone"
    assert config.batch_limit_mb == 300
    assert config.skip_aae is True


@patch("os.path.exists", return_value=True)
def test_load_yaml(mock_exists):
    yaml_content = """
device_name: "Test YAML Device"
batch_limit_mb: 500
skip_aae: false
"""
    with patch("builtins.open", mock_open(read_data=yaml_content)):
        config = AppConfig.load(config_path="test.yaml")
        assert config.device_name == "Test YAML Device"
        assert config.batch_limit_mb == 500
        assert config.skip_aae is False


@patch(
    "os.environ",
    {
        "MEDIA_ICOPY_DEVICE_NAME": "Env Device",
        "MEDIA_ICOPY_BATCH_LIMIT_MB": "1000",
        "MEDIA_ICOPY_SKIP_AAE": "false",
    },
)
def test_load_env():
    # Will use defaults since no file is patched
    config = AppConfig.load(config_path="nonexistent.yaml")
    assert config.device_name == "Env Device"
    assert config.batch_limit_mb == 1000
    assert config.skip_aae is False


def test_load_overrides():
    config = AppConfig.load(
        config_path="nonexistent.yaml",
        device_name="Override Device",
        batch_limit_mb=999,
    )
    assert config.device_name == "Override Device"
    assert config.batch_limit_mb == 999


@patch("os.path.exists", return_value=True)
def test_load_invalid_yaml(mock_exists):
    invalid_yaml = "device_name: [unclosed list"
    with patch("builtins.open", mock_open(read_data=invalid_yaml)):
        # Should fallback to defaults
        config = AppConfig.load(config_path="test.yaml")
        assert config.device_name == "Apple iPhone"


def test_save(tmp_path):
    config = AppConfig(device_name="Save Test", batch_limit_mb=123)
    save_path = tmp_path / "config.yaml"
    config.save(str(save_path))

    with open(save_path, "r") as f:
        data = yaml.safe_load(f)

    assert data["device_name"] == "Save Test"
    assert data["batch_limit_mb"] == 123
