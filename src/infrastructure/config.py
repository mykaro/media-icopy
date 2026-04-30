"""Configuration management for the iPhone copier."""

import logging
import os
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..paths import resource_path, user_data_path


@dataclass
class AppConfig:
    """Application configuration container."""

    dest_root: str | None = None
    device_name: str = "Apple iPhone"
    source_folders: list[str] = field(default_factory=lambda: ["DCIM"])
    batch_limit_mb: int = 300
    retry_attempts: int = 3
    retry_backoff_seconds: list[int] = field(default_factory=lambda: [1, 5, 15])
    db_path: str = "./session.db"
    log_path: str = "./logs/events.log"
    log_level: str = "INFO"
    dry_run: bool = False
    skip_aae: bool = True  # Ignore Apple Adjustment Extension files (.aae)
    language: str = "auto"  # auto | uk | en

    @classmethod
    def load(cls, config_path: str | None = None, **overrides: Any) -> "AppConfig":
        """
        Loads configuration with the following priority:
        GUI Overrides > Env Variables > YAML Config > Defaults
        """
        data: dict[str, Any] = {}

        # 1. Load from YAML if exists
        # First try user config, then fallback to bundled defaults
        user_config = user_data_path("config", "defaults.yaml")
        default_config = resource_path("config", "defaults.yaml")
        
        path_to_load = config_path or user_config
        if not os.path.exists(path_to_load) and not config_path:
            path_to_load = default_config

        if os.path.exists(path_to_load):
            with open(path_to_load, "r", encoding="utf-8") as f:
                try:
                    yaml_data = yaml.safe_load(f)
                    if yaml_data:
                        data.update(yaml_data)
                except yaml.YAMLError as e:
                    logging.getLogger(__name__).error(
                        f"Failed to parse config '{path_to_load}': {e}. Using defaults."
                    )

        # 2. Load from Env Variables (IPHONE_COPIER_*)
        for key in cls.__dataclass_fields__:
            env_key = f"MEDIA_ICOPY_{key.upper()}"
            if env_key in os.environ:
                env_val = os.environ[env_key]
                # Check bool before int: in Python bool is a subclass of int,
                # so isinstance(False, int) is True — bool must be checked first.
                field_default = cls.__dataclass_fields__[key].default
                if isinstance(field_default, bool):
                    data[key] = env_val.lower() in ("true", "1", "yes")
                elif isinstance(field_default, int):
                    data[key] = int(env_val)
                else:
                    data[key] = env_val

        # 3. Apply Explicit Overrides (GUI)
        data.update({k: v for k, v in overrides.items() if v is not None})

        # Resolve paths to be absolute (relative to user data dir)
        config = cls(**data)
        if config.db_path.startswith("./"):
            config.db_path = user_data_path(config.db_path[2:])
        if config.log_path.startswith("./"):
            config.log_path = user_data_path(config.log_path[2:])

        return config

    def save(self, config_path: str | None = None):
        """Saves current configuration to YAML in the user data directory."""
        if config_path is None:
            config_path = user_data_path("config", "defaults.yaml")
            
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        # Convert dataclass to dict, but handle field factories if any
        data = {k: getattr(self, k) for k in self.__dataclass_fields__}
        
        # Turn absolute paths back into relative ones for portability in the yaml
        if isinstance(data.get("db_path"), str) and os.path.isabs(data["db_path"]):
            data["db_path"] = "./session.db"
        if isinstance(data.get("log_path"), str) and os.path.isabs(data["log_path"]):
            data["log_path"] = "./logs/events.log"

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False)
