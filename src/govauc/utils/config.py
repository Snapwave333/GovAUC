"""
Configuration management for GovAUC.
"""

import json
import os
from pathlib import Path
from typing import Any, Optional


def get_default_config() -> dict[str, Any]:
    """Get default configuration."""
    return {
        "database": {
            "url": "sqlite:///govauc.db",
        },
        "scraping": {
            "default_rate_limit": 2.0,
            "max_concurrent_requests": 10,
            "user_agent_rotation": True,
            "retry_attempts": 3,
        },
        "analysis": {
            "min_profit_threshold": 100,
            "min_roi_percentage": 50,
            "confidence_threshold": 0.5,
            "gem_score_threshold": 0.8,
        },
        "sniping": {
            "enabled": False,  # Must be explicitly enabled
            "default_snipe_seconds": 30,
            "max_concurrent_snipes": 5,
            "auto_schedule_gems": False,
        },
        "budget": {
            "total_budget": 10000.0,
            "max_per_item": 1000.0,
            "reserve_percentage": 20,  # Keep 20% as reserve
        },
        "notifications": {
            "enabled": True,
            "email": None,
            "slack_webhook": None,
            "urgency_levels": ["high", "critical"],
        },
        "sites": [],  # Will be populated with auction sites
        "api_keys": {
            "ebay_app_id": "",
            "kbb_api_key": "",
            "openai_api_key": "",
            "anthropic_api_key": "",
        },
    }


def load_config(config_path: Optional[str] = None) -> dict[str, Any]:
    """
    Load configuration from file.

    Args:
        config_path: Path to config file (default: config/config.json)

    Returns:
        Configuration dictionary
    """
    if config_path is None:
        config_path = os.path.join(os.getcwd(), "config", "config.json")

    path = Path(config_path)

    if path.exists():
        with open(path, "r") as f:
            user_config = json.load(f)

        # Merge with defaults
        config = get_default_config()
        _deep_merge(config, user_config)
        return config
    else:
        return get_default_config()


def save_config(config: dict[str, Any], config_path: Optional[str] = None):
    """
    Save configuration to file.

    Args:
        config: Configuration dictionary
        config_path: Path to save config (default: config/config.json)
    """
    if config_path is None:
        config_path = os.path.join(os.getcwd(), "config", "config.json")

    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        json.dump(config, f, indent=2)


def _deep_merge(base: dict, override: dict):
    """Deep merge override into base dictionary."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
