"""
Configuration handling: env vars first, YAML fallback for local dev.
"""

import logging
import os

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")


def load_config(config_path=None):
    """Load configuration from env vars with YAML fallback."""
    config = {}

    # Try YAML file first as base
    yaml_path = config_path or DEFAULT_CONFIG_PATH
    if os.path.exists(yaml_path):
        try:
            with open(yaml_path, "r") as f:
                config = yaml.safe_load(f) or {}
            logger.info(f"Loaded base config from {yaml_path}")
        except Exception as e:
            logger.warning(f"Could not load YAML config: {e}")

    # Env vars override YAML
    if os.environ.get("DATABASE_URL"):
        config.setdefault("database", {})["url"] = os.environ["DATABASE_URL"]

    if os.environ.get("DATABASE_PATH"):
        config.setdefault("database", {})["path"] = os.environ["DATABASE_PATH"]

    if os.environ.get("LLM_MODEL"):
        config.setdefault("llm", {})["model"] = os.environ["LLM_MODEL"]

    if os.environ.get("LOG_LEVEL"):
        config.setdefault("logging", {})["level"] = os.environ["LOG_LEVEL"]

    return config
