#!/usr/bin/env python3
"""
Cross-Platform Build & Installer Automation Script for Argus PII Guard v1.0.0.

Usage:
    python build_app.py

Performs:
1. Icon asset verification & conversion.
2. PyInstaller execution using argus_pii_guard.spec.
3. Windows Inno Setup installer compilation (if ISCC.exe is available).
4. Release archive creation (.zip / .tar.gz) in dist/installers/.
"""

import os
import sys
import shutil
import subprocess
import platform
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "dist"
INSTALLERS_DIR = DIST_DIR / "installers"
VERSION = "1.0.5"


def print_step(title):
    print(f"\n========================================================")
    print(f"  {title}")
    print(f"========================================================\n")


def check_prerequisites():
    print_step("1. Checking Prerequisites")
    try:
        import PyInstaller
        print(f"[OK] PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("[!] PyInstaller is not installed. Installing via pip...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # Ensure PIL is installed for icon handling
    try:
        import PIL
        print(f"[OK] Pillow version: {PIL.__version__}")
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pillow"])


def prepare_icons():
    print_step("2. Verifying & Generating Application Icons")
    assets_dir = BASE_DIR / "frontend" / "assets"
    ico_path = assets_dir / "argus-icon.ico"
    png_path = assets_dir / "argus-icon.png"

    if not ico_path.exists() and png_path.exists():
        print(f"Generating {ico_path.name} from {png_path.name}...")
        from PIL import Image
        img = Image.open(png_path)
        img.save(ico_path, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
        print(f"[OK] Created {ico_path}")
    else:
        print(f"[OK] Application icon verified at: {ico_path}")


def clean_directory(dir_path):
    """Safely remove a directory tree handling Windows read-only permissions."""
    if not dir_path.exists():
        return
    def on_rm_error(func, path, exc_info):
        try:
            os.chmod(path, 0o777)
            func(path)
        except Exception:
            pass
    shutil.rmtree(dir_path, onerror=on_rm_error)


def run_pyinstaller():
    print_step("3. Executing PyInstaller Bundle Compilation")
    spec_file = BASE_DIR / "argus_pii_guard.spec"
    
    # Pre-clean dist and build targets safely to prevent Windows file lock permission errors
    target_build = BASE_DIR / "build" / "argus_pii_guard"
    clean_directory(target_build)
    target_bundle = DIST_DIR / "Argus PII Guard"
    clean_directory(target_bundle)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(spec_file),
        "--noconfirm"
    ]
    print(f"Running: {' '.join(cmd)}")
    subprocess.check_call(cmd, cwd=str(BASE_DIR))
    print("[OK] PyInstaller build completed successfully.")


def build_windows_installer():
    print_step("4. Building Windows Setup Installer (Inno Setup)")
    if sys.platform != "win32":
        print("Skipping Inno Setup (not running on Windows).")
        return

    iss_file = BASE_DIR / "installer" / "windows_installer.iss"
    if not iss_file.exists():
        print(f"Warning: Inno Setup file not found at {iss_file}")
        return

    # Look for ISCC.exe in standard paths
    iscc_candidates = [
        "iscc",
        "ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
    ]

    iscc_bin = None
    for candidate in iscc_candidates:
        bin_path = shutil.which(candidate) or candidate
        if os.path.exists(bin_path):
            iscc_bin = bin_path
            break

    if iscc_bin:
        print(f"Found Inno Setup compiler: {iscc_bin}")
        INSTALLERS_DIR.mkdir(parents=True, exist_ok=True)
        cmd = [iscc_bin, str(iss_file)]
        print(f"Running: {' '.join(cmd)}")
        subprocess.check_call(cmd, cwd=str(BASE_DIR))
        print(f"[OK] Windows Setup Installer compiled: {INSTALLERS_DIR / 'Argus_PII_Guard_v1.0.0_Setup.exe'}")
    else:
        print("[!] Inno Setup (ISCC.exe) not found on PATH or standard program directories.")
        print("    Install Inno Setup (https://jrsoftware.org/isinfo.php) to automatically build Argus_PII_Guard_v1.0.0_Setup.exe.")


def create_release_archive():
    print_step("5. Creating Release Archive")
    INSTALLERS_DIR.mkdir(parents=True, exist_ok=True)
    bundle_dir = DIST_DIR / "Argus PII Guard"

    if bundle_dir.exists():
        archive_name = f"Argus_PII_Guard_v{VERSION}_{platform.system().lower()}"
        archive_format = "zip" if sys.platform == "win32" else "gztar"
        archive_path = shutil.make_archive(
            str(INSTALLERS_DIR / archive_name),
            archive_format,
            root_dir=str(DIST_DIR),
            base_dir="Argus PII Guard"
        )
        print(f"[OK] Release archive created: {archive_path}")


def main():
    print(f"\n========================================================")
    print(f"  Argus PII Guard v{VERSION} Build & Packaging Engine")
    print(f"========================================================")

    check_prerequisites()
    prepare_icons()
    run_pyinstaller()
    build_windows_installer()
    create_release_archive()

    print_step("Build Complete")
    print(f"Output files located in: {DIST_DIR.resolve()}")
    if INSTALLERS_DIR.exists():
        for item in INSTALLERS_DIR.iterdir():
            print(f" - {item.name} ({round(item.stat().st_size / (1024*1024), 2)} MB)")


if __name__ == "__main__":
    main()
