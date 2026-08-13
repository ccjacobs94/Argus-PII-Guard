# Building & Packaging Argus PII Guard v1.1.0

This guide provides instructions for building standalone desktop application bundles and installers for **Windows**, **macOS**, and **Linux**.

---

## Prerequisites

1. **Python**: Python 3.10+ (Python 3.11/3.12 recommended).
2. **Dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install pyinstaller
   ```

---

## Quick Build (Automated)

Run the automated build script:

```bash
python build_app.py
```

The script will:
1. Verify Python & PyInstaller environment.
2. Ensure application icons are generated.
3. Package the Python backend and `frontend/` static assets into a standalone folder: `dist/Argus PII Guard/`.
4. Bundle native installer payloads (`installer/native_installer.py` and `installer/install.sh`).
5. On Windows (if Inno Setup is installed), compile `dist/installers/Argus_PII_Guard_v1.1.0_Setup.exe`.
6. Compress release archives (`.zip` / `.tar.gz`) into `dist/installers/`.

---

## Platform Specific Build Details

### Windows

- **PyInstaller Executable**:
  ```bash
  pyinstaller argus_pii_guard.spec --noconfirm --clean
  ```
  Output: `dist/Argus PII Guard/Argus PII Guard.exe`

- **Inno Setup Windows Installer**:
  1. Download and install [Inno Setup 6](https://jrsoftware.org/isinfo.php).
  2. Compile the installer script:
     ```cmd
     "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\windows_installer.iss
     ```
  3. Output: `dist/installers/Argus_PII_Guard_v1.0.0_Setup.exe`

---

### macOS

- **PyInstaller App Bundle**:
  ```bash
  pyinstaller argus_pii_guard.spec --noconfirm --clean
  ```
- **dmg Creation**:
  Use `create-dmg` or standard macOS Disk Utility to wrap `dist/Argus PII Guard.app` into `Argus_PII_Guard_v1.0.0.dmg`.

---

### Linux

- **PyInstaller Binary**:
  ```bash
  pyinstaller argus_pii_guard.spec --noconfirm --clean
  ```
- **AppImage / tar.gz**:
  Compress `dist/Argus PII Guard/` into `Argus_PII_Guard_v1.0.0_linux.tar.gz`.

---

## Verification & Testing Built Packages

To run automated unit & integration tests before packaging:

```bash
pytest --cov=backend --cov-report=term-missing --cov-fail-under=85
```
