"""
State and configuration management for Argus PII Guard.

Provides persistent storage and safe loading/saving for:
- Application configuration settings (settings.json)
- Historical scan findings (results.json)
- Fast incremental scanning checksum cache (cache.json)
"""

import copy
import json
import os
from typing import Any

SETTINGS_FILE = "settings.json"
RESULTS_FILE = "results.json"
CACHE_FILE = "cache.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    "folders": [],  # List of target directory paths to scan
    "ollama_address": "http://127.0.0.1:11434",
    "auto_delete": False,
    "schedule": {
        "enabled": False,
        "time": "02:00",  # HH:MM (24-hour format)
    },
    "concurrency": "auto",
    "image_optimization": "medium",
    "text_scan_mode": "regex_llm",
    "tour_completed": False,
    # Model provider: "ollama" or "local_gguf"
    "model_provider": "ollama",
    # Path to directory containing local .gguf model files
    "models_folder": "",
    # Selected local GGUF model filenames
    "local_vision_model": "",
    "local_text_model": "",
    # Ollama model names
    "vision_model_name": "gemma4:12b",
    "text_model_name": "gemma4:12b",
    # Remediation & Redaction settings
    "redaction_mask_pattern": "redacted",  # "redacted", "mask", "confidential"
    "deletion_mode": "trash",  # "trash" (Recycle Bin / Trash) or "permanent"
    "backup_retention_days": 7,
    "allowed_exceptions": [],  # List of whitelisted findings/files
}


def _read_json(file_path: str, default: Any) -> Any:
    """Safely reads and parses a JSON file, returning `default` on missing or corrupt files."""
    if not os.path.exists(file_path):
        return default
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return default


def _write_json(file_path: str, data: Any) -> None:
    """Atomically serializes and writes data to a JSON file with pretty indentation."""
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def load_settings() -> dict[str, Any]:
    """Loads application settings from disk, filling in any missing keys with defaults."""
    loaded = _read_json(SETTINGS_FILE, default={})
    if not isinstance(loaded, dict):
        loaded = {}

    settings = copy.deepcopy(DEFAULT_SETTINGS)
    settings.update(loaded)
    return settings


def save_settings(settings: dict[str, Any]) -> None:
    """Saves application settings to disk."""
    _write_json(SETTINGS_FILE, settings)


def load_results() -> list[dict[str, Any]]:
    """Loads historical scan results from disk."""
    results = _read_json(RESULTS_FILE, default=[])
    return results if isinstance(results, list) else []


def save_results(results: list[dict[str, Any]]) -> None:
    """Saves scan results to disk."""
    _write_json(RESULTS_FILE, results)


def load_cache() -> dict[str, Any]:
    """Loads the file inspection cache from disk."""
    cache = _read_json(CACHE_FILE, default={})
    return cache if isinstance(cache, dict) else {}


def save_cache(cache: dict[str, Any]) -> None:
    """Saves the file inspection cache to disk."""
    _write_json(CACHE_FILE, cache)
