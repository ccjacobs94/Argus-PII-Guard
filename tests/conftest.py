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


@pytest.fixture
def mock_winreg():
    """
    On non-Windows platforms (Linux CI / macOS), `winreg` does not exist as a
    built-in module. Pre-injects a MagicMock into sys.modules.
    """
    import sys
    import platform
    from unittest.mock import MagicMock
    if platform.system() != "Windows":
        fake_winreg = MagicMock()
        fake_winreg.HKEY_CURRENT_USER = 0x80000001
        fake_winreg.HKEY_LOCAL_MACHINE = 0x80000002
        fake_winreg.KEY_READ = 0x20019
        fake_winreg.KEY_WRITE = 0x20006
        fake_winreg.REG_EXPAND_SZ = 2
        fake_winreg.REG_SZ = 1
        fake_winreg.REG_DWORD = 4
        sys.modules["winreg"] = fake_winreg
        yield fake_winreg
        del sys.modules["winreg"]
    else:
        import winreg
        yield winreg


@pytest.fixture
def mock_ctypes_windll():
    """
    On non-Windows platforms (Linux CI / macOS), `ctypes.windll` does not exist.
    Pre-injects a MagicMock into ctypes.windll so dotted patch targets resolve.
    """
    import ctypes
    from unittest.mock import MagicMock
    if not hasattr(ctypes, "windll"):
        fake_windll = MagicMock()
        ctypes.windll = fake_windll
        yield fake_windll
        del ctypes.windll
    else:
        yield ctypes.windll
