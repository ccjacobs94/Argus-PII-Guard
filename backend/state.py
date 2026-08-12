import json
import os
from pathlib import Path

SETTINGS_FILE = "settings.json"
RESULTS_FILE = "results.json"

def load_settings():
    defaults = {
        "folders": [], # List of folders to scan
        "ollama_address": "http://127.0.0.1:11434",
        "auto_delete": False,
        "schedule": {
            "enabled": False,
            "time": "02:00" # HH:MM
        },
        "concurrency": "auto",
        "image_optimization": "medium",
        "text_scan_mode": "regex_llm",
        "tour_completed": False,
        # Model provider: "ollama" or "local_gguf"
        "model_provider": "ollama",
        # Path to folder containing .gguf model files
        "models_folder": "",
        # Selected local GGUF model filenames
        "local_vision_model": "",
        "local_text_model": "",
        # Ollama model names (previously hardcoded in scanner.py)
        "vision_model_name": "gemma4:12b",
        "text_model_name": "gemma4:12b",
        # Remediation & Redaction settings
        "redaction_mask_pattern": "redacted", # "redacted", "mask", "confidential"
        "deletion_mode": "trash", # "trash" (Recycle bin) or "permanent"
        "backup_retention_days": 7,
        "allowed_exceptions": [], # List of {"id", "file", "pattern", "match_text", "added_at", "reason"}
    }
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            try:
                loaded = json.load(f)
                # Merge loaded with defaults
                for k, v in defaults.items():
                    if k not in loaded:
                        loaded[k] = v
                return loaded
            except:
                pass
    return defaults

def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)

def load_results():
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, "r") as f:
            try:
                return json.load(f)
            except:
                pass
    return []

def save_results(results):
    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=4)

CACHE_FILE = "cache.json"

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            try:
                return json.load(f)
            except:
                pass
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=4)
