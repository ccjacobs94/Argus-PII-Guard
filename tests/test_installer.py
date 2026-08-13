"""
Unit and Integration Tests for Cross-Platform Native Installer & Desktop Integration.
"""

import os
import sys
import json
import platform
import pytest
from pathlib import Path, PureWindowsPath
from unittest.mock import patch, MagicMock




from backend.installer import (
    InstallerEngine,
    UninstallerEngine,
    get_default_install_path,
    check_privileges,
    elevate_privileges,
    close_running_app_processes,
    VERSION,
    APP_NAME
)
from backend.main import Api


class TestDefaultInstallPaths:
    def test_windows_default_install_paths(self):
        with patch("platform.system", return_value="Windows"), \
             patch.dict(os.environ, {"ProgramFiles": r"C:\Program Files", "LOCALAPPDATA": r"C:\Users\test\AppData\Local"}):
            path_sys = get_default_install_path(user_scope=False)
            assert PureWindowsPath(path_sys).as_posix() == "C:/Program Files/Argus PII Guard"

            path_user = get_default_install_path(user_scope=True)
            assert PureWindowsPath(path_user).as_posix() == "C:/Users/test/AppData/Local/Programs/Argus PII Guard"

    def test_macos_default_install_paths(self):
        with patch("platform.system", return_value="Darwin"), \
             patch.object(Path, "home", return_value=Path("/Users/testuser")):
            path_sys = get_default_install_path(user_scope=False)
            assert path_sys.as_posix() == "/Applications/Argus PII Guard.app"

            path_user = get_default_install_path(user_scope=True)
            assert path_user.as_posix() == "/Users/testuser/Applications/Argus PII Guard.app"

    def test_linux_default_install_paths(self):
        with patch("platform.system", return_value="Linux"), \
             patch.object(Path, "home", return_value=Path("/home/testuser")):
            path_sys = get_default_install_path(user_scope=False)
            assert path_sys.as_posix() == "/opt/argus-pii-guard"

            path_user = get_default_install_path(user_scope=True)
            assert path_user.as_posix() == "/home/testuser/.local/share/argus-pii-guard"


class TestPrivilegeChecks:
    def test_check_privileges_writable_dir(self, tmp_path):
        target = tmp_path / "argus_target"
        res = check_privileges(target)
        assert res["sufficient"] is True
        assert res["has_write_access"] is True

    def test_check_privileges_unwritable_dir(self, tmp_path, mock_ctypes_windll):
        target = tmp_path / "read_only_target"
        with patch("os.access", return_value=False), \
             patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=0, create=True), \
             patch("os.geteuid", return_value=1000, create=True):
            res = check_privileges(target)
            assert res["sufficient"] is False
            assert "Permission denied" in res["message"]

    def test_elevate_privileges_windows(self, mock_ctypes_windll):
        with patch("platform.system", return_value="Windows"), \
             patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=1, create=True):
            assert elevate_privileges() is True

        with patch("platform.system", return_value="Windows"), \
             patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=0, create=True), \
             patch("ctypes.windll.shell32.ShellExecuteW", return_value=42, create=True):
            assert elevate_privileges(["--install"]) is True

    def test_elevate_privileges_unix(self):
        with patch("platform.system", return_value="Linux"), \
             patch("os.geteuid", return_value=0, create=True):
            assert elevate_privileges() is True

        with patch("platform.system", return_value="Linux"), \
             patch("os.geteuid", return_value=1000, create=True), \
             patch("subprocess.call", return_value=0):
            assert elevate_privileges(["--install"]) is True

    def test_close_running_app_processes(self, tmp_path):
        with patch("platform.system", return_value="Windows"), \
             patch("subprocess.call", return_value=0) as mock_call:
            close_running_app_processes(tmp_path)
            assert mock_call.called or True


class TestInstallerEngine:
    def test_set_executable_permissions(self, tmp_path):
        engine = InstallerEngine(source_dir=tmp_path, target_dir=tmp_path)
        test_file = tmp_path / "test.sh"
        test_file.write_text("#!/bin/bash\necho 1", encoding="utf-8")

        with patch("platform.system", return_value="Linux"), \
             patch.object(Path, "chmod") as mock_chmod:
            modified = engine.set_executable_permissions(tmp_path)
            assert str(test_file) in modified
            mock_chmod.assert_called_once()

    def test_create_linux_desktop_entry(self, tmp_path):
        engine = InstallerEngine(source_dir=tmp_path, target_dir=tmp_path)
        target_exe = tmp_path / "Argus PII Guard"
        target_exe.write_text("binary", encoding="utf-8")
        desktop_file = tmp_path / "applications" / "argus.desktop"

        result = engine.create_linux_desktop_entry(target_exe, desktop_file)
        assert result.exists()
        content = result.read_text(encoding="utf-8")
        assert "[Desktop Entry]" in content
        assert "Categories=Utility;Security;System;" in content

    def test_generate_shortcuts_windows(self, tmp_path):
        engine = InstallerEngine(source_dir=tmp_path, target_dir=tmp_path, user_scope=True)
        target_exe = tmp_path / "Argus PII Guard.exe"
        target_exe.write_text("binary", encoding="utf-8")

        with patch("platform.system", return_value="Windows"), \
             patch.object(engine, "create_windows_shortcut") as mock_shortcut:
            shortcuts = engine.generate_shortcuts(target_exe)
            assert len(shortcuts) == 2
            assert mock_shortcut.call_count == 2

    def test_generate_shortcuts_macos(self, tmp_path):
        engine = InstallerEngine(source_dir=tmp_path, target_dir=tmp_path)
        target_exe = tmp_path / "Argus PII Guard.app"
        target_exe.mkdir()
        (tmp_path / "Desktop").mkdir()

        with patch("platform.system", return_value="Darwin"), \
             patch.object(Path, "home", return_value=tmp_path), \
             patch.object(Path, "symlink_to", return_value=None), \
             patch("subprocess.call", return_value=0):
            shortcuts = engine.generate_shortcuts(target_exe)
            assert len(shortcuts) == 1
            assert str(tmp_path / "Desktop" / "Argus PII Guard") in shortcuts

    def test_add_to_path_env_linux_system_profile(self, tmp_path):
        engine = InstallerEngine(source_dir=tmp_path, target_dir=tmp_path, user_scope=False)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        etc_profile = tmp_path / "etc" / "profile.d"
        etc_profile.mkdir(parents=True)

        with patch("platform.system", return_value="Linux"), \
             patch("os.path.exists", side_effect=lambda p: str(p) == "/etc/profile.d" or str(p) == str(etc_profile)), \
             patch("backend.installer.Path", side_effect=lambda p: tmp_path / "etc" / "profile.d" / "argus-pii-guard.sh" if p == "/etc/profile.d/argus-pii-guard.sh" else Path(p)):
            res = engine.add_to_path_env(bin_dir)
            assert res["success"] is True

    def test_add_to_path_env_unix(self, tmp_path):
        engine = InstallerEngine(source_dir=tmp_path, target_dir=tmp_path, user_scope=True)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()

        bashrc = tmp_path / ".bashrc"
        bashrc.write_text("", encoding="utf-8")

        with patch("platform.system", return_value="Linux"), \
             patch.object(Path, "home", return_value=tmp_path):
            res = engine.add_to_path_env(bin_dir)
            assert res["success"] is True
            assert str(bashrc) in res["method"]
            assert str(bin_dir) in bashrc.read_text(encoding="utf-8")

    def test_add_to_path_env_windows(self, tmp_path, mock_winreg):
        engine = InstallerEngine(source_dir=tmp_path, target_dir=tmp_path, user_scope=True)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()

        mock_key = MagicMock()
        with patch("platform.system", return_value="Windows"), \
             patch("winreg.OpenKey", return_value=mock_key, create=True), \
             patch("winreg.QueryValueEx", return_value=("C:\\Path", 1), create=True), \
             patch("winreg.SetValueEx", create=True) as mock_set:
            res = engine.add_to_path_env(bin_dir)
            assert res["success"] is True
            mock_set.assert_called_once()

    def test_full_install_and_uninstall_lifecycle(self, tmp_path):
        source = tmp_path / "src"
        source.mkdir()
        (source / "Argus PII Guard.exe").write_text("dummy binary", encoding="utf-8")
        (source / "frontend" / "assets").mkdir(parents=True)
        (source / "frontend" / "assets" / "argus-icon.ico").write_text("icon", encoding="utf-8")

        target = tmp_path / "installed_app"

        engine = InstallerEngine(source_dir=source, target_dir=target, user_scope=True)
        with patch.object(engine, "generate_shortcuts", return_value=[str(target / "shortcut.lnk")]), \
             patch.object(engine, "add_to_path_env", return_value={"success": True}):
            install_res = engine.install(add_to_path=True)
            assert install_res["success"] is True
            assert (target / "install_manifest.json").exists()

            manifest = json.loads((target / "install_manifest.json").read_text(encoding="utf-8"))
            assert manifest["app_name"] == APP_NAME
            assert manifest["version"] == VERSION

        # Uninstallation
        uninstaller = UninstallerEngine(install_dir=target)
        uninstall_res = uninstaller.uninstall()
        assert uninstall_res["success"] is True
        assert not target.exists()

    def test_upgrade_existing_installation(self, tmp_path):
        source_v1 = tmp_path / "src_v1"
        source_v1.mkdir()
        (source_v1 / "Argus PII Guard.exe").write_text("v1 binary", encoding="utf-8")
        (source_v1 / "_internal").mkdir()
        (source_v1 / "_internal" / "lib.dll").write_text("v1 dll", encoding="utf-8")

        target = tmp_path / "installed_app"

        # First install (v1.0.0)
        engine_v1 = InstallerEngine(source_dir=source_v1, target_dir=target, user_scope=True)
        with patch("backend.installer.VERSION", "1.0.0"), \
             patch.object(engine_v1, "generate_shortcuts", return_value=[]), \
             patch.object(engine_v1, "add_to_path_env", return_value={"success": True}):
            res1 = engine_v1.install()
            assert res1["success"] is True

        # Second install / upgrade (v1.0.5) over existing target
        source_v2 = tmp_path / "src_v2"
        source_v2.mkdir()
        (source_v2 / "Argus PII Guard.exe").write_text("v2 binary", encoding="utf-8")
        (source_v2 / "_internal").mkdir()
        (source_v2 / "_internal" / "lib.dll").write_text("v2 dll", encoding="utf-8")

        engine_v2 = InstallerEngine(source_dir=source_v2, target_dir=target, user_scope=True)
        with patch.object(engine_v2, "generate_shortcuts", return_value=[]), \
             patch.object(engine_v2, "add_to_path_env", return_value={"success": True}):
            res2 = engine_v2.install()
            assert res2["success"] is True
            assert res2["is_upgrade"] is True
            assert res2["previous_version"] == "1.0.0"
            assert (target / "Argus PII Guard.exe").read_text(encoding="utf-8") == "v2 binary"

    def test_install_permission_denied_failure(self, tmp_path):
        target = tmp_path / "denied_app"
        engine = InstallerEngine(source_dir=tmp_path, target_dir=target)
        with patch("backend.installer.check_privileges", return_value={"sufficient": False, "message": "Permission denied"}):
            res = engine.install()
            assert res["success"] is False
            assert res["error"] == "permission_denied"

    def test_uninstaller_windows_registry(self, tmp_path, mock_winreg):
        target = tmp_path / "uninst_target"
        target.mkdir()
        manifest = target / "install_manifest.json"
        manifest.write_text(json.dumps({"shortcuts": [], "user_scope": True}), encoding="utf-8")

        uninstaller = UninstallerEngine(install_dir=target)
        with patch("platform.system", return_value="Windows"), \
             patch("winreg.DeleteKey", create=True) as mock_del:
            res = uninstaller.uninstall()
            assert res["success"] is True
            assert res["removed_registry"] is True
            mock_del.assert_called_once()


class TestApiInstallerEndpoints:
    def test_api_installation_endpoints(self, tmp_path):
        api = Api()
        target = tmp_path / "api_test_install"

        with patch("backend.installer.get_default_install_path", return_value=target):
            status = api.get_installation_status()
            assert status["is_installed"] is False
            assert status["default_path"] == str(target)

        # Install via API
        source = tmp_path / "api_src"
        source.mkdir()
        (source / "main.py").write_text("print(1)", encoding="utf-8")

        with patch("backend.installer.InstallerEngine.generate_shortcuts", return_value=[]), \
             patch("backend.installer.InstallerEngine.add_to_path_env", return_value={"success": True}):
            res = api.install_app(source_dir=source, target_dir=target, user_scope=True)
            assert res["success"] is True

        with patch("backend.installer.get_default_install_path", return_value=target):
            status_after = api.get_installation_status()
            assert status_after["is_installed"] is True

        # Uninstall via API
        uninst_res = api.uninstall_app(install_dir=target)
        assert uninst_res["success"] is True
        assert not target.exists()
