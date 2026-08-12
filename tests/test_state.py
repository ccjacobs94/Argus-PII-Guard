import os
import json
from backend.state import (
    load_settings, save_settings,
    load_results, save_results,
    load_cache, save_cache,
    SETTINGS_FILE, RESULTS_FILE, CACHE_FILE
)

def test_load_settings_defaults():
    settings = load_settings()
    assert isinstance(settings, dict)
    assert "folders" in settings
    assert settings["folders"] == []
    assert settings["ollama_address"] == "http://127.0.0.1:11434"
    assert settings["concurrency"] == "auto"
    assert settings["tour_completed"] is False

def test_save_and_load_settings():
    custom = {
        "folders": ["C:/TestFolder"],
        "ollama_address": "http://192.168.1.50:11434",
        "concurrency": "4",
        "image_optimization": "low",
        "text_scan_mode": "regex_only",
        "auto_delete": True
    }
    save_settings(custom)
    loaded = load_settings()
    assert loaded["folders"] == ["C:/TestFolder"]
    assert loaded["concurrency"] == "4"
    assert loaded["auto_delete"] is True
    # Verify default fields merged
    assert "schedule" in loaded

def test_load_settings_corrupt_file(tmp_path, monkeypatch):
    import backend.state as state
    corrupt_file = tmp_path / "corrupt_settings.json"
    corrupt_file.write_text("invalid json content {{{")
    monkeypatch.setattr(state, "SETTINGS_FILE", str(corrupt_file))
    
    settings = load_settings()
    assert isinstance(settings, dict)
    assert settings["concurrency"] == "auto"

def test_save_and_load_results():
    assert load_results() == []
    sample_results = [
        {"file": "test1.txt", "type": "Text", "reason": "SSN found"},
        {"file": "test2.png", "type": "Image", "reason": "Credit card"}
    ]
    save_results(sample_results)
    assert load_results() == sample_results

def test_load_results_corrupt(tmp_path, monkeypatch):
    import backend.state as state
    corrupt_file = tmp_path / "corrupt_results.json"
    corrupt_file.write_text("invalid json {{{")
    monkeypatch.setattr(state, "RESULTS_FILE", str(corrupt_file))
    assert load_results() == []

def test_save_and_load_cache():
    assert load_cache() == {}
    cache_data = {
        "C:/file1.txt": {"mtime": 123456.0, "result": {"compromised": False}},
        "C:/file2.png": {"mtime": 789101.0, "result": {"compromised": True, "reason": "Passport"}}
    }
    save_cache(cache_data)
    loaded = load_cache()
    assert loaded == cache_data
    assert loaded["C:/file1.txt"]["result"]["compromised"] is False

def test_load_cache_corrupt(tmp_path, monkeypatch):
    import backend.state as state
    corrupt_file = tmp_path / "corrupt_cache.json"
    corrupt_file.write_text("invalid json {{{")
    monkeypatch.setattr(state, "CACHE_FILE", str(corrupt_file))
    assert load_cache() == {}
