# Argus PII Guard v1.0.0 — General Availability Release 🎉

Welcome to the official **v1.0.0 release** of **Argus PII Guard**, an on-device Data Loss Prevention (DLP) & Privacy Sentinel. Argus PII Guard scans local documents, codebases, logs, images, and receipts for sensitive Personally Identifiable Information (PII), database credentials, API keys, and financial secrets — keeping **100% of your data private on your local hardware**.

---

## 🚀 Key Highlights & Feature Matrix

### 🛡️ Dual AI Model Engines
- **Ollama Local & Remote Integration**: Connect to local or remote Ollama servers (`llama3.2:3b`, `qwen2.5-coder`, `llava`).
- **Built-in Native GGUF Engine**: Run `.gguf` quantized models directly on CPU or NVIDIA GPUs via `llama-cpp-python` — zero dependency on external Ollama installations.

### ⚡ Smart Hardware Profiling & One-Click Downloader
- **Hardware Benchmarking**: Auto-detects CPU cores, RAM, and NVIDIA VRAM to calculate a 0–100 hardware fit score.
- **Hugging Face Downloader**: Download recommended GGUF vision and text models directly from Hugging Face with real-time download speed, progress bar, and cancellation support.
- **Auto-Discovery**: Scans local model directories instantly for new GGUF files.

### 🔬 Deep Visualizer & File Inspection
- **Text & Code Highlights**: Highlighting of regex and AI PII matches with exact character bounds, line numbers, and match counts.
- **Image Bounding Box Annotations**: Dynamic visual bounding boxes overlaying sensitive text on photo IDs, credit cards, and receipts.

### ⏰ Background Sentinel & Incremental Sweeps
- **Incremental MD5 Scanning**: Fast hashing skips unchanged files automatically, reducing repeat scan time by up to 95%.
- **Background Daily Sweeps**: Configurable daily background scans with auto-remediation (deletion/quarantine) options.

### 🎓 Interactive Product Tour Engine
- Guided step-by-step onboarding walkthrough introducing layout controls, hardware profiling, scanner settings, and preview visualizer features.

---

## 📋 Release Change Log (v1.0.0 Initial Build)

- **Initial Commit**: Complete desktop GUI build with HTML5/CSS3 frontend and Python backend API (`pywebview`).
- **Scanner Engine**: Full support for `.txt`, `.csv`, `.json`, `.env`, `.py`, `.js`, `.pdf`, `.docx`, `.png`, `.jpg`, `.jpeg`, and `.heic`.
- **Validation**: 120 automated unit tests passing with **86.14% code coverage** (`pytest --cov=backend`).
- **Build Pipeline**: PyInstaller specification (`argus_pii_guard.spec`) and automated installer compiler (`build_app.py`).

---

## 📦 Download Assets

| Asset Name | Platform | Description |
| :--- | :--- | :--- |
| `Argus_PII_Guard_v1.0.0_windows.zip` | Windows 10/11 (64-bit) | Standalone release package bundle |
| `Argus_PII_Guard_v1.0.0_Setup.exe` | Windows 10/11 (64-bit) | GUI Setup Wizard (Inno Setup) |
| `Source code (zip / tar.gz)` | Cross-Platform | Full open-source repository |

---

## 🔒 100% On-Device Privacy Guarantee
Argus PII Guard runs **completely offline**. No document contents, scanned images, or extracted secrets leave your local device.
