# Argus PII Guard v1.1.0 — Minor Feature & System Enhancement Release 🚀

Welcome to the **v1.1.0 release** of **Argus PII Guard**, bringing major enhancements to sensitive data detection, automated document remediation, incremental scanner performance, cross-platform native installer integration, and modern GUI compatibility.

---

## 🌟 Highlights & Key Enhancements in v1.1.0

### 📦 Cross-Platform Native Setup Wizard & Installer Suite
- **GUI Setup Wizard (`native_installer.py`)**: Tkinter-powered desktop installation wizard with automated elevation checks, system vs. user scope support, desktop/Start menu shortcut creation, and registry integration.
- **Uninstaller & Upgrade Manager**: Automatic detection and clean removal or upgrade of previous installations.

### 🔐 3-Tier Smart Secret & Credential Detection
- **High-Entropy Secret Analyzer**: Multi-algorithm entropy calculations (Shannon & Kolmogorov complexity) to detect API keys, private certificates, database connection strings, and access tokens.
- **Pattern & Context Heuristics**: Identifies secrets embedded in `.env`, `.json`, `.py`, `.js`, and config files with zero external network calls.
- **Memory-Safe Secret Masking**: Obfuscates secrets in local state and UI previews to prevent secret leakage in logs.

### 🧹 In-Place Document Redaction & Cleansing Engine
- **Multi-Format In-Place Redaction**: Supports redacting identified PII and secrets directly in-place across `.txt`, `.pdf`, `.docx`, `.xlsx`, and `.pptx` documents.
- **Exception Whitelisting**: Allows users to mark false positives as safe exceptions (`.argusignore`) with support for masked and unmasked match resolution.
- **Safe File Deletion & Trashing**: System trash and permanent file purging capabilities with file integrity verification before operating on files.

### ⚡ Checksum Change Detection & Auto-Rescanning
- **SHA-256 Checksum Engine**: Tracks modified files automatically across directory scans.
- **Incremental Efficiency**: Skips unaltered files while instantly triggering re-scans for modified or updated local documents.

### 🐛 PyWebView & CI Infrastructure Updates
- **PyWebView FileDialog Enum Update**: Replaced deprecated `FOLDER_DIALOG` constants with `webview.FileDialog.FOLDER`.
- **Scan Abort & Rescan Directory Lifecycle**: Resolved scan cancellation state management bugs and directory rescan lifecycle issues.

---

## 📋 Release Change Log (v1.0.5 → v1.1.0)

- **bump(version)**: Update system version to `v1.1.0` across backend installer sentinel, packaging scripts, Inno Setup manifests, and documentation.
- **feat(installer)**: Native Tkinter installer & uninstaller integration with multi-platform CLI launcher support.
- **feat(secrets)**: Implement 3-tier secret analysis pipeline for high-entropy tokens and credentials.
- **feat(remediation)**: Add in-place document redaction (`.docx`, `.xlsx`, `.pptx`, `.pdf`, `.txt`) and exception filtering.
- **feat(scanner)**: SHA-256 checksum file change detection and incremental re-scanning.
- **fix(gui)**: Update deprecated `webview.FOLDER_DIALOG` to `webview.FileDialog.FOLDER`.
- **fix(ci)**: Comprehensive cross-platform GitHub Actions validation pipeline with automated test suite.

---

## 📦 Release Packages & Assets

| Asset Name | Platform | Description |
| :--- | :--- | :--- |
| `Argus_PII_Guard_v1.1.0_Setup.exe` | Windows 10/11 (64-bit) | GUI Setup Wizard (Inno Setup) |
| `Argus_PII_Guard_v1.1.0_windows.zip` | Windows 10/11 (64-bit) | Portable Standalone Bundle & Native Installer |
| `Source code (zip / tar.gz)` | Cross-Platform | Full Open-Source Repository |

---

## 🔒 100% On-Device Privacy Guarantee
Argus PII Guard runs **completely offline**. No document contents, scanned images, or extracted secrets ever leave your local device.
