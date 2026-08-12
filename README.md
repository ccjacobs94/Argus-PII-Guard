# Argus PII Guard 🛡️

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/ccjacobs94/Argus-PII-Guard/releases/tag/v1.0.0)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Coverage](https://img.shields.io/badge/coverage-85%25%2B-brightgreen.svg)](VALIDATION_PIPELINE.md)

**Argus PII Guard** is an open-source, on-device **Data Loss Prevention (DLP) & Privacy Sentinel**. It scans local documents, codebases, logs, images, and scanned receipts for sensitive Personally Identifiable Information (PII), database credentials, API keys, and financial data — keeping **100% of your data private on your local hardware**.

---

## 🌟 Key Features

- 🤖 **Dual Local AI Engines**:
  - **Ollama Integration**: Connect seamlessly to any local or remote Ollama instance (e.g., `llama3.2:3b`, `qwen2.5-coder`).
  - **Built-in Local GGUF Engine**: Run `.gguf` models directly on CPU or NVIDIA GPU via `llama-cpp-python` — zero dependency on Ollama installations.
- ⚡ **Smart Hardware Profiling**:
  - Auto-detects CPU cores, total RAM, and NVIDIA VRAM.
  - Computes a hardware fit score (0–100) and recommends optimal local AI vision/text models.
- 📥 **One-Click Model Downloader**:
  - Download recommended GGUF models directly from Hugging Face with real-time progress, speed tracking, and cancellation support.
- 🔬 **Deep Visualizer & Previews**:
  - **Text & Code Highlights**: Inline regex and AI detection overlays with exact match bounds and line navigation.
  - **Image Bounding Boxes**: Visual bounding box overlays over credit cards, driver's licenses, and photo IDs.
- ⏰ **Automated Background Sentinel**:
  - **Incremental Scans**: MD5 hash change detection ensures untouched files are scanned instantly without re-processing.
  - **Scheduled Daily Sweeps**: Configurable daily background scans with automated email or system notifications.
  - **Auto-Remediation**: Optional deletion or quarantine of verified compromised files.
- 🎓 **Interactive Onboarding Tour Engine**:
  - Built-in interactive product walkthrough guiding new users through system layout, model setup, and scanning options.

---

## 💻 Installation & Usage

### Option 1: Running Pre-Built Windows Desktop Application
1. Download the latest installer `Argus_PII_Guard_v1.0.0_Setup.exe` from the [Releases](https://github.com/ccjacobs94/Argus-PII-Guard/releases/tag/v1.0.0) page.
2. Run the setup wizard to install Argus PII Guard to your Desktop and Start Menu.
3. Launch **Argus PII Guard**.

---

### Option 2: Running from Source (Developer Setup)

#### 1. Prerequisites
- Python 3.10 or higher
- Git

#### 2. Clone Repository & Setup Virtual Environment
```bash
git clone https://github.com/ccjacobs94/Argus-PII-Guard.git
cd Argus-PII-Guard

# Create and activate a virtual environment
python -m venv venv

# Windows (PowerShell)
.\venv\Scripts\Activate.ps1

# Linux / macOS
source venv/bin/activate
```

#### 3. Install Dependencies
```bash
pip install -r requirements.txt
```
*(If `requirements.txt` is not present, install core dependencies directly: `pip install pywebview eel pillow requests psutil pytest pytest-cov llama-cpp-python`)*

#### 4. Launch Application
```bash
python -m backend.main
```

---

## 🧪 Testing & Validation

Argus PII Guard maintains a strict zero-regression policy and minimum 85% test coverage requirement across all backend packages.

To run the automated validation suite:
```bash
pytest --cov=backend --cov-report=term-missing --cov-fail-under=85
```

For full testing guidelines and architectural validation details, refer to [VALIDATION_PIPELINE.md](file:///c:/Users/ccjac/OneDrive/Documents/Development_Projects/PII-Manager/VALIDATION_PIPELINE.md).

---

## 📦 Packaging & Building Executables

To compile the standalone PyInstaller bundle and Inno Setup installer:
```bash
python build_app.py
```
Outputs are generated in `dist/` and `dist/installers/`. See [BUILD.md](file:///c:/Users/ccjac/OneDrive/Documents/Development_Projects/PII-Manager/BUILD.md) for full packaging documentation.

---

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

1. **Fork the repository** and create a feature branch (`git checkout -b feature/amazing-feature`).
2. Ensure all changes pass the full test suite with $\ge 85\%$ coverage (`pytest --cov=backend --cov-fail-under=85`).
3. If introducing new UI views or scanner capabilities, synchronize step definitions in [frontend/script.js](file:///c:/Users/ccjac/OneDrive/Documents/Development_Projects/PII-Manager/frontend/script.js) and [frontend/index.html](file:///c:/Users/ccjac/OneDrive/Documents/Development_Projects/PII-Manager/frontend/index.html) to keep the interactive onboarding tour updated.
4. Commit your changes (`git commit -m "feat: add amazing feature"`).
5. Push to your branch and open a Pull Request.

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.

---

## 🔒 Privacy Guarantee

Argus PII Guard operates **entirely offline and on-device**. No file content, extracted text, scanned images, or detection logs are ever transmitted over the network or sent to remote cloud telemetry services.
