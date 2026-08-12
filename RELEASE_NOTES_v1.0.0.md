# Argus PII Guard — Release Notes v1.0.0 🎉

**Release Date:** August 2026  
**Build:** 1.0.0 (Official General Availability)

Argus PII Guard is an **On-Device Data Loss Prevention & Privacy Sentinel** designed to scan, detect, visualize, and remediate sensitive Personally Identifiable Information (PII) and credentials across local documents, images, logs, and repositories — keeping your data 100% private and on your hardware.

---

## Key Highlights & Features in v1.0.0

### 🛡️ Dual AI Model Engines (Ollama + Built-in Local GGUF)
- **Ollama Integration**: Connect seamlessly to any local or remote Ollama server instance.
- **Built-in Local GGUF Engine**: Run local GGUF models directly via `llama-cpp-python` — zero dependency on Ollama installations.

### ⚡ One-Click Model Installation & Recommendations
- **Hardware Profiling**: Automatically detects CPU, RAM, and NVIDIA GPU VRAM to suggest optimal models.
- **One-Click HF Downloads**: Download GGUF models from Hugging Face directly into your specified `models_folder` with real-time download speed and progress bars.
- **Discovered Model Auto-Detection**: Instant scanning of your model directory.

### 🔬 Deep Visualizer & Previews
- **Text & Code Highlights**: Visual inline regex and AI detection overlays with exact match counts.
- **Image Bounding Box Overlay**: Renders interactive bounding boxes over detected IDs, credit cards, and sensitive document photos.

### ⏰ Automated Background Sentinel & Incremental Scans
- **Incremental Scanning**: MD5 hash-based change detection ensures untouched files are scanned instantly without re-processing.
- **Background Daily Sweeps**: Configurable scheduled scans at user-specified times.
- **Automatic Remediation**: Optional auto-deletion of verified compromised files.

### 🎓 Interactive Onboarding Tour Engine
- Guided step-by-step product walkthrough introducing layout, scanning modes, deep visualizer, hardware profiling, and local model setup.

---

## Desktop Installers & Packages

- **Windows Setup**: `Argus_PII_Guard_v1.0.0_Setup.exe` (GUI setup wizard with desktop shortcut and Start Menu entry).
- **Portable Zip**: `Argus_PII_Guard_v1.0.0_windows.zip`
- **macOS / Linux**: Standalone bundle release packages.
