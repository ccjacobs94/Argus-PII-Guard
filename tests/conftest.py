import pytest
import os
import tempfile
import shutil
from pathlib import Path
import backend.state as state
import backend.scanner as scanner

@pytest.fixture(autouse=True)
def isolate_state_files(monkeypatch, tmp_path):
    """
    Redirect state and cache files to a temporary directory for each test
    to guarantee test isolation and prevent modifying real state.
    """
    temp_settings = tmp_path / "settings.json"
    temp_results = tmp_path / "results.json"
    temp_cache = tmp_path / "cache.json"

    monkeypatch.setattr(state, "SETTINGS_FILE", str(temp_settings))
    monkeypatch.setattr(state, "RESULTS_FILE", str(temp_results))
    monkeypatch.setattr(state, "CACHE_FILE", str(temp_cache))

    # Reset scanner state
    scanner.scan_state.reset()
    yield tmp_path
