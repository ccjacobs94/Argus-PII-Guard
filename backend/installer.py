"""
Cross-Platform Native Installer & Desktop Integration Module for Argus PII Guard.

Provides:
- Target system directory resolution (Windows, macOS, Linux).
- Privilege & permission escalation detection.
- Extraction & deployment to platform-standard directories.
- Shortcut creation (Start Menu, Desktop, XDG Applications, Launchpad).
- System PATH environment variable updates.
- Registry & install manifest creation.
- Clean uninstallation and cleanup engine.
"""

import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

VERSION = "1.1.0"
APP_NAME = "Argus PII Guard"
APP_ID = "argus.piiguard.sentinel.1.0"
PUBLISHER = "Argus Security Team"
DESKTOP_ENTRY_NAME = "argus-pii-guard.desktop"

EXCLUDE_NAMES = {
    ".git", ".github", ".pytest_cache", "__pycache__", "venv", ".venv", "env",
    "build", "dist", ".vscode", ".idea", ".agents", ".coverage", "cache.json",
    "results.json", "settings.json", "install_manifest.json",
}


def get_default_install_path(user_scope: bool = False) -> Path:
    """Returns platform-standard application installation directory."""
    system_os = platform.system()
    if system_os == "Windows":
        if user_scope:
            local_appdata = os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))
            return Path(local_appdata) / "Programs" / APP_NAME
        prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        return Path(prog_files) / APP_NAME

    elif system_os == "Darwin":  # macOS
        if user_scope:
            return Path.home() / "Applications" / f"{APP_NAME}.app"
        return Path("/Applications") / f"{APP_NAME}.app"

    else:  # Linux / Unix
        if user_scope:
            return Path.home() / ".local" / "share" / "argus-pii-guard"
        return Path("/opt") / "argus-pii-guard"


def check_privileges(target_path: Union[str, Path], user_scope: bool = False) -> dict[str, Any]:
    """
    Detects required system rights based on target path and scope.
    Returns status dict indicating privilege sufficiency.
    """
    path = Path(target_path).resolve()
    check_dir = path
    while not check_dir.exists() and check_dir.parent != check_dir:
        check_dir = check_dir.parent

    has_write_access = os.access(str(check_dir), os.W_OK)
    is_admin = False

    if platform.system() == "Windows":
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            is_admin = False
    else:
        is_admin = (os.geteuid() == 0) if hasattr(os, "geteuid") else False

    target_str = str(path).lower()
    is_protected_system_dir = (
        "program files" in target_str
        or "programdata" in target_str
        or target_str.startswith(("/opt", "/usr", "/etc"))
    )

    sufficient = is_admin if is_protected_system_dir else (has_write_access or is_admin)

    if not sufficient:
        msg = (
            f"Permission denied: Insufficient write privileges for '{path}'. "
            f"Please run the installer with administrative/elevated rights (UAC or sudo), "
            f"or specify a user-scope directory."
        )
    else:
        msg = f"Privilege check passed for target path '{path}'."

    return {
        "sufficient": sufficient,
        "is_admin": is_admin,
        "has_write_access": has_write_access,
        "target_path": str(path),
        "message": msg,
    }


def elevate_privileges(args: Optional[list[str]] = None) -> bool:
    """Requests privilege escalation if required rights are missing."""
    if args is None:
        args = sys.argv[1:]

    system_os = platform.system()
    if system_os == "Windows":
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
            if is_admin:
                return True
            script = sys.argv[0]
            cmd_args = " ".join([f'"{arg}"' for arg in args])
            ret = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, f'"{script}" {cmd_args}', None, 1
            )
            return ret > 32
        except Exception:
            return False
    else:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            return True
        try:
            cmd = ["sudo", sys.executable, sys.argv[0]] + args
            return subprocess.call(cmd) == 0
        except Exception:
            return False


def close_running_app_processes(target_dir: Optional[Union[str, Path]] = None) -> None:
    """Closes running instances of Argus PII Guard prior to install, upgrade, or uninstall."""
    target_str = str(Path(target_dir).resolve()).lower() if target_dir else ""
    try:
        import psutil
        for proc in psutil.process_iter(["pid", "name", "exe"]):
            try:
                proc_name = proc.info.get("name") or ""
                proc_exe = proc.info.get("exe") or ""
                is_target = (
                    (proc_name and APP_NAME in proc_name)
                    or (proc_exe and APP_NAME in proc_exe)
                    or (target_str and proc_exe and target_str in proc_exe.lower())
                )
                if is_target and proc.pid != os.getpid():
                    proc.terminate()
                    proc.wait(timeout=1.5)
            except Exception:
                pass
    except Exception:
        pass

    if platform.system() == "Windows":
        try:
            subprocess.call(
                ["taskkill", "/F", "/IM", f"{APP_NAME}.exe"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass


class InstallerEngine:
    """Cross-platform installation & desktop integration engine."""

    def __init__(
        self,
        source_dir: Optional[Union[str, Path]] = None,
        target_dir: Optional[Union[str, Path]] = None,
        user_scope: bool = False,
    ) -> None:
        src_path = Path(source_dir).resolve() if source_dir else Path.cwd().resolve()

        dist_bundle = src_path / "dist" / APP_NAME
        target_bin_name = f"{APP_NAME}.exe" if platform.system() == "Windows" else APP_NAME
        if dist_bundle.exists() and (dist_bundle / target_bin_name).exists():
            src_path = dist_bundle

        self.source_dir = src_path
        self.user_scope = user_scope
        self.target_dir = Path(target_dir).resolve() if target_dir else get_default_install_path(user_scope)

    def set_executable_permissions(self, install_path: Path) -> list[str]:
        """Sets chmod +x execution permissions on Unix binaries and scripts."""
        modified = []
        if platform.system() == "Windows":
            return modified

        executable_extensions = {"", ".sh", ".py", ".bin"}
        for root, _, files in os.walk(install_path):
            for file_name in files:
                file_path = Path(root) / file_name
                if file_path.suffix.lower() in executable_extensions or file_name == APP_NAME:
                    try:
                        current_mode = file_path.stat().st_mode
                        file_path.chmod(current_mode | 0o755)
                        modified.append(str(file_path))
                    except Exception as e:
                        print(f"Warning: Could not set chmod on {file_path}: {e}")
        return modified

    def create_windows_shortcut(self, target_exe: Path, shortcut_path: Path, icon_path: Optional[Path] = None) -> None:
        """Creates Windows .lnk shortcut using PowerShell WScript.Shell COM object."""
        shortcut_path.parent.mkdir(parents=True, exist_ok=True)
        icon_str = str(icon_path) if icon_path and icon_path.exists() else str(target_exe)

        ps_script = (
            f"$ws = New-Object -ComObject WScript.Shell; "
            f"$s = $ws.CreateShortcut('{shortcut_path}'); "
            f"$s.TargetPath = '{target_exe}'; "
            f"$s.WorkingDirectory = '{target_exe.parent}'; "
            f"$s.IconLocation = '{icon_str}'; "
            f"$s.Save()"
        )
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script]
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def create_linux_desktop_entry(
        self,
        target_exe: Path,
        desktop_file_path: Path,
        icon_path: Optional[Path] = None,
    ) -> Path:
        """Generates XDG Desktop Entry file for Linux applications."""
        desktop_file_path.parent.mkdir(parents=True, exist_ok=True)
        icon_str = str(icon_path) if icon_path and icon_path.exists() else "security-high"

        content = f"""[Desktop Entry]
Type=Application
Name={APP_NAME}
Comment=Argus PII Detection & Remediation Engine
Exec="{target_exe}" %F
Icon={icon_str}
Terminal=false
Categories=Utility;Security;System;
StartupWMClass=argus-pii-guard
"""
        desktop_file_path.write_text(content, encoding="utf-8")
        try:
            desktop_file_path.chmod(0o755)
        except Exception:
            pass

        if shutil.which("update-desktop-database"):
            try:
                subprocess.call(
                    ["update-desktop-database", str(desktop_file_path.parent)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

        return desktop_file_path

    def generate_shortcuts(self, target_exe: Path, icon_path: Optional[Path] = None) -> list[str]:
        """Generates platform-specific desktop and start menu shortcuts."""
        created_shortcuts: list[str] = []
        system_os = platform.system()

        if system_os == "Windows":
            if self.user_scope:
                desktop_dir = Path(os.path.expanduser(r"~\Desktop"))
                start_menu_dir = (
                    Path(os.environ.get("APPDATA", os.path.expanduser(r"~\AppData\Roaming")))
                    / "Microsoft" / "Windows" / "Start Menu" / "Programs" / APP_NAME
                )
            else:
                desktop_dir = Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop"
                start_menu_dir = (
                    Path(os.environ.get("ProgramData", r"C:\ProgramData"))
                    / "Microsoft" / "Windows" / "Start Menu" / "Programs" / APP_NAME
                )

            desktop_lnk = desktop_dir / f"{APP_NAME}.lnk"
            start_menu_lnk = start_menu_dir / f"{APP_NAME}.lnk"

            try:
                self.create_windows_shortcut(target_exe, desktop_lnk, icon_path)
                created_shortcuts.append(str(desktop_lnk))
            except Exception as e:
                user_desktop = Path(os.path.expanduser(r"~\Desktop")) / f"{APP_NAME}.lnk"
                try:
                    self.create_windows_shortcut(target_exe, user_desktop, icon_path)
                    created_shortcuts.append(str(user_desktop))
                except Exception:
                    print(f"Warning: Failed to create desktop shortcut: {e}")

            try:
                self.create_windows_shortcut(target_exe, start_menu_lnk, icon_path)
                created_shortcuts.append(str(start_menu_lnk))
            except Exception as e:
                user_start = (
                    Path(os.environ.get("APPDATA", os.path.expanduser(r"~\AppData\Roaming")))
                    / "Microsoft" / "Windows" / "Start Menu" / "Programs" / APP_NAME / f"{APP_NAME}.lnk"
                )
                try:
                    self.create_windows_shortcut(target_exe, user_start, icon_path)
                    created_shortcuts.append(str(user_start))
                except Exception:
                    print(f"Warning: Failed to create start menu shortcut: {e}")

        elif system_os == "Darwin":  # macOS
            desktop_dir = Path.home() / "Desktop"
            desktop_shortcut = desktop_dir / APP_NAME
            try:
                if desktop_shortcut.exists() or desktop_shortcut.is_symlink():
                    desktop_shortcut.unlink()
                desktop_shortcut.symlink_to(target_exe)
                created_shortcuts.append(str(desktop_shortcut))
            except Exception as e:
                print(f"Warning: Failed to create macOS desktop link: {e}")

            lsregister = "/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister"
            if os.path.exists(lsregister):
                try:
                    subprocess.call([lsregister, "-f", str(self.target_dir)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass

        else:  # Linux
            apps_dir = Path.home() / ".local" / "share" / "applications" if self.user_scope else Path("/usr/share/applications")
            app_desktop = apps_dir / DESKTOP_ENTRY_NAME
            desktop_shortcut = Path.home() / "Desktop" / DESKTOP_ENTRY_NAME

            try:
                self.create_linux_desktop_entry(target_exe, app_desktop, icon_path)
                created_shortcuts.append(str(app_desktop))
            except Exception as e:
                print(f"Warning: Failed to create XDG application menu entry: {e}")

            try:
                self.create_linux_desktop_entry(target_exe, desktop_shortcut, icon_path)
                created_shortcuts.append(str(desktop_shortcut))
            except Exception as e:
                print(f"Warning: Failed to create Linux desktop entry: {e}")

        return created_shortcuts

    def add_to_path_env(self, bin_dir: Path) -> dict[str, Any]:
        """Adds binary directory to system or user PATH environment variable."""
        system_os = platform.system()
        bin_dir_str = str(bin_dir)
        result: dict[str, Any] = {"success": True, "method": "", "path": bin_dir_str}

        if system_os == "Windows":
            try:
                import winreg
                hive = winreg.HKEY_CURRENT_USER if self.user_scope else winreg.HKEY_LOCAL_MACHINE
                key_path = "Environment" if self.user_scope else r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"

                with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
                    try:
                        current_path, _ = winreg.QueryValueEx(key, "Path")
                    except FileNotFoundError:
                        current_path = ""

                    paths = [p.strip() for p in current_path.split(";") if p.strip()]
                    if bin_dir_str not in paths:
                        new_path = ";".join(paths + [bin_dir_str])
                        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
                        result["method"] = "Windows Registry"
                    else:
                        result["method"] = "Already present in Registry"
            except Exception as e:
                result["success"] = False
                result["error"] = str(e)

        else:
            if not self.user_scope and os.path.exists("/etc/profile.d"):
                profile_script = Path("/etc/profile.d/argus-pii-guard.sh")
                try:
                    profile_script.write_text(f'export PATH="$PATH:{bin_dir_str}"\n', encoding="utf-8")
                    result["method"] = str(profile_script)
                except Exception as e:
                    result["success"] = False
                    result["error"] = str(e)
            else:
                shell_rc = Path.home() / ".bashrc"
                try:
                    rc_content = shell_rc.read_text(encoding="utf-8") if shell_rc.exists() else ""
                    export_line = f'export PATH="$PATH:{bin_dir_str}"'
                    if export_line not in rc_content:
                        with shell_rc.open("a", encoding="utf-8") as f:
                            f.write(f"\n# Argus PII Guard PATH\n{export_line}\n")
                        result["method"] = str(shell_rc)
                    else:
                        result["method"] = "Already present in shell rc"
                except Exception as e:
                    result["success"] = False
                    result["error"] = str(e)

        return result

    def register_windows_uninstall(self, target_dir: Path, target_exe: Path, icon_path: Optional[Path] = None) -> str:
        """Registers application in Windows Add/Remove Programs registry."""
        if platform.system() != "Windows":
            return ""

        try:
            import winreg
            hive = winreg.HKEY_CURRENT_USER if self.user_scope else winreg.HKEY_LOCAL_MACHINE
            sub_key = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\ArgusPIIGuard"

            uninstaller_exe = target_dir / "installer" / "native_installer.py"
            if not uninstaller_exe.exists():
                uninstaller_exe = target_dir / "native_installer.py"
            uninstall_cmd = f'"{sys.executable}" "{uninstaller_exe}" --uninstall'

            try:
                key = winreg.CreateKey(hive, sub_key)
            except PermissionError:
                hive = winreg.HKEY_CURRENT_USER
                key = winreg.CreateKey(hive, sub_key)

            with key:
                winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
                winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, VERSION)
                winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, PUBLISHER)
                winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(target_dir))
                winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, uninstall_cmd)
                winreg.SetValueEx(key, "QuietUninstallString", 0, winreg.REG_SZ, f"{uninstall_cmd} --quiet")
                if icon_path and icon_path.exists():
                    winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, str(icon_path))
                winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)

            hive_name = "HKCU" if hive == winreg.HKEY_CURRENT_USER else "HKLM"
            return f"Registry key: {hive_name}\\{sub_key}"
        except Exception as e:
            print(f"Warning: Failed to register Windows uninstall key: {e}")
            return ""

    def install(self, add_to_path: bool = True) -> dict[str, Any]:
        """Executes full cross-platform installation & upgrade workflow."""
        priv_check = check_privileges(self.target_dir)
        if not priv_check["sufficient"]:
            return {
                "success": False,
                "error": "permission_denied",
                "message": priv_check["message"],
            }

        close_running_app_processes(self.target_dir)

        manifest_path = self.target_dir / "install_manifest.json"
        is_upgrade = manifest_path.exists()
        previous_version = None

        if is_upgrade:
            try:
                prev_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                previous_version = prev_manifest.get("version", "Unknown")
            except Exception:
                previous_version = "Unknown"

        installed_files: list[str] = []
        self.target_dir.mkdir(parents=True, exist_ok=True)

        def _copy_with_chmod(src: str, dst: str, *, follow_symlinks: bool = True) -> None:
            if os.path.exists(dst):
                try:
                    os.chmod(dst, 0o777)
                except Exception:
                    pass
            try:
                shutil.copy2(src, dst, follow_symlinks=follow_symlinks)
            except PermissionError as pe:
                close_running_app_processes(self.target_dir)
                time.sleep(0.5)
                try:
                    if os.path.exists(dst):
                        os.chmod(dst, 0o777)
                    shutil.copy2(src, dst, follow_symlinks=follow_symlinks)
                except Exception:
                    raise PermissionError(
                        f"Cannot overwrite '{Path(dst).name}' because Argus PII Guard is currently running. "
                        f"Please close Argus PII Guard and retry."
                    ) from pe

        if self.source_dir.exists():
            for item in self.source_dir.iterdir():
                if item.name in EXCLUDE_NAMES or item.name.startswith("."):
                    continue
                if item.resolve() == self.target_dir.resolve():
                    continue

                target_item = self.target_dir / item.name

                if item.is_dir():
                    if target_item.exists():
                        for root, _, files in os.walk(target_item):
                            for f in files:
                                try:
                                    os.chmod(os.path.join(root, f), 0o777)
                                except Exception:
                                    pass
                    shutil.copytree(
                        item,
                        target_item,
                        dirs_exist_ok=True,
                        copy_function=_copy_with_chmod,
                        ignore=shutil.ignore_patterns(*EXCLUDE_NAMES, "*.pyc", "*.pyo", "*.tmp"),
                    )
                else:
                    _copy_with_chmod(str(item), str(target_item))
                installed_files.append(str(target_item))

        executable_files = self.set_executable_permissions(self.target_dir)

        exe_names = [f"{APP_NAME}.exe", APP_NAME, "main.py", "argus_pii_guard"]
        target_exe = None
        for candidate in exe_names:
            c_path = self.target_dir / candidate
            if c_path.exists():
                target_exe = c_path
                break
        if not target_exe:
            target_exe = self.target_dir / (f"{APP_NAME}.exe" if platform.system() == "Windows" else APP_NAME)

        assets_ico = self.target_dir / "frontend" / "assets" / "argus-icon.ico"
        assets_png = self.target_dir / "frontend" / "assets" / "argus-icon.png"
        icon_path = assets_ico if assets_ico.exists() else assets_png

        shortcuts = self.generate_shortcuts(target_exe, icon_path)
        path_res = self.add_to_path_env(self.target_dir) if add_to_path else {}
        reg_key = self.register_windows_uninstall(self.target_dir, target_exe, icon_path)

        manifest_data = {
            "app_name": APP_NAME,
            "version": VERSION,
            "publisher": PUBLISHER,
            "is_upgrade": is_upgrade,
            "previous_version": previous_version,
            "install_time": datetime.now(timezone.utc).isoformat(),
            "target_dir": str(self.target_dir),
            "user_scope": self.user_scope,
            "target_exe": str(target_exe),
            "installed_files": installed_files,
            "executable_files": executable_files,
            "shortcuts": shortcuts,
            "registry_key": reg_key,
            "path_integration": path_res,
        }

        manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

        return {
            "success": True,
            "is_upgrade": is_upgrade,
            "previous_version": previous_version,
            "install_dir": str(self.target_dir),
            "manifest_path": str(manifest_path),
            "shortcuts_created": len(shortcuts),
            "manifest": manifest_data,
        }


class UninstallerEngine:
    """Clean uninstallation & resource cleanup engine."""

    def __init__(self, install_dir: Optional[Union[str, Path]] = None) -> None:
        self.install_dir = Path(install_dir).resolve() if install_dir else get_default_install_path()

    def uninstall(self) -> dict[str, Any]:
        close_running_app_processes(self.install_dir)
        manifest_path = self.install_dir / "install_manifest.json"
        removed_shortcuts: list[str] = []
        removed_registry = False
        removed_path = False

        manifest: dict[str, Any] = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                manifest = {}

        for sc in manifest.get("shortcuts", []):
            sc_path = Path(sc)
            if sc_path.exists() or sc_path.is_symlink():
                try:
                    sc_path.unlink()
                    removed_shortcuts.append(sc)
                except Exception as e:
                    print(f"Warning: Could not remove shortcut {sc}: {e}")

        if platform.system() == "Windows":
            try:
                import winreg
                user_scope = manifest.get("user_scope", False)
                hive = winreg.HKEY_CURRENT_USER if user_scope else winreg.HKEY_LOCAL_MACHINE
                sub_key = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\ArgusPIIGuard"
                winreg.DeleteKey(hive, sub_key)
                removed_registry = True
            except Exception:
                pass

        if platform.system() != "Windows" and os.path.exists("/etc/profile.d/argus-pii-guard.sh"):
            try:
                os.remove("/etc/profile.d/argus-pii-guard.sh")
                removed_path = True
            except Exception:
                pass

        if self.install_dir.exists():
            try:
                shutil.rmtree(self.install_dir, ignore_errors=True)
            except Exception as e:
                print(f"Warning: Could not remove install dir {self.install_dir}: {e}")

        return {
            "success": True,
            "install_dir": str(self.install_dir),
            "removed_shortcuts": removed_shortcuts,
            "removed_registry": removed_registry,
            "removed_path": removed_path,
            "message": f"Successfully uninstalled Argus PII Guard from {self.install_dir}",
        }
