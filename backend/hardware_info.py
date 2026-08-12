"""
Hardware detection and model recommendation engine for Argus PII Guard.

Provides comprehensive system profiling (RAM, CPU, GPU) and a curated catalog
of GGUF models with hardware-aware fit-score recommendations.
"""

import os
import sys
import subprocess
import platform
import math


# ---------------------------------------------------------------------------
# Curated Model Catalog
# ---------------------------------------------------------------------------
# Each entry describes a publicly available GGUF model suitable for PII
# detection tasks (vision and/or text).  Fields:
#   name          – human-readable model identifier
#   filename      – canonical GGUF filename on HuggingFace
#   params_b      – parameter count in billions
#   quant         – quantisation label (e.g. Q4_K_M)
#   size_gb       – approximate file size in GB
#   min_ram_gb    – minimum RAM to load the model at all
#   rec_ram_gb    – recommended RAM for comfortable inference
#   vision        – whether the model can do image analysis
#   description   – short blurb for the UI card
#   url           – HuggingFace download page

MODEL_CATALOG = [
    # --- Small / Edge models (≤ 8 GB RAM) ---
    {
        "name": "Qwen2.5-1.5B",
        "filename": "qwen2.5-1.5b-instruct-q8_0.gguf",
        "params_b": 1.5,
        "quant": "Q8_0",
        "size_gb": 1.6,
        "min_ram_gb": 4,
        "rec_ram_gb": 6,
        "vision": False,
        "description": "Ultra-light text model, great for quick regex-verified PII checks on constrained hardware.",
        "url": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF",
        "download_url": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q8_0.gguf"
    },
    {
        "name": "Phi-4 Mini",
        "filename": "phi-4-mini-instruct-q4_k_m.gguf",
        "params_b": 3.8,
        "quant": "Q4_K_M",
        "size_gb": 2.3,
        "min_ram_gb": 4,
        "rec_ram_gb": 8,
        "vision": False,
        "description": "Microsoft's compact reasoning model. Excellent for code-secret and credential detection.",
        "url": "https://huggingface.co/microsoft/Phi-4-mini-instruct-gguf",
        "download_url": "https://huggingface.co/microsoft/Phi-4-mini-instruct-gguf/resolve/main/phi-4-mini-instruct-q4_k_m.gguf"
    },
    {
        "name": "Moondream2",
        "filename": "moondream2-text-model-f16.gguf",
        "params_b": 1.9,
        "quant": "F16",
        "size_gb": 3.7,
        "min_ram_gb": 6,
        "rec_ram_gb": 8,
        "vision": True,
        "description": "Tiny vision-language model optimised for image understanding. Good for ID card & document detection.",
        "url": "https://huggingface.co/vikhyatk/moondream2",
        "download_url": "https://huggingface.co/vikhyatk/moondream2/resolve/main/moondream2-text-model-f16.gguf"
    },
    {
        "name": "Gemma 3 1B",
        "filename": "gemma-3-1b-it-q8_0.gguf",
        "params_b": 1.0,
        "quant": "Q8_0",
        "size_gb": 1.1,
        "min_ram_gb": 4,
        "rec_ram_gb": 6,
        "vision": False,
        "description": "Google's smallest Gemma. Fast text PII scanning with minimal resource usage.",
        "url": "https://huggingface.co/google/gemma-3-1b-it",
        "download_url": "https://huggingface.co/google/gemma-3-1b-it/resolve/main/gemma-3-1b-it-q8_0.gguf"
    },
    # --- Mid-range models (8–16 GB RAM) ---
    {
        "name": "Gemma 3 4B",
        "filename": "gemma-3-4b-it-q4_k_m.gguf",
        "params_b": 4.0,
        "quant": "Q4_K_M",
        "size_gb": 2.5,
        "min_ram_gb": 6,
        "rec_ram_gb": 10,
        "vision": True,
        "description": "Multimodal Gemma with vision. Good balance of speed and accuracy for PII image + text inspection.",
        "url": "https://huggingface.co/google/gemma-3-4b-it",
        "download_url": "https://huggingface.co/google/gemma-3-4b-it/resolve/main/gemma-3-4b-it-q4_k_m.gguf"
    },
    {
        "name": "Mistral 7B Instruct",
        "filename": "mistral-7b-instruct-v0.3-q4_k_m.gguf",
        "params_b": 7.0,
        "quant": "Q4_K_M",
        "size_gb": 4.1,
        "min_ram_gb": 8,
        "rec_ram_gb": 12,
        "vision": False,
        "description": "Strong general-purpose text model. Reliable for PII classification and secret detection.",
        "url": "https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.3",
        "download_url": "https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.3/resolve/main/mistral-7b-instruct-v0.3-q4_k_m.gguf"
    },
    {
        "name": "Qwen2.5 7B",
        "filename": "qwen2.5-7b-instruct-q4_k_m.gguf",
        "params_b": 7.0,
        "quant": "Q4_K_M",
        "size_gb": 4.4,
        "min_ram_gb": 8,
        "rec_ram_gb": 12,
        "vision": False,
        "description": "High-quality multilingual text model. Strong at structured output and JSON compliance.",
        "url": "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF",
        "download_url": "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf"
    },
    {
        "name": "LLaVA v1.6 Mistral 7B",
        "filename": "llava-v1.6-mistral-7b-q4_k_m.gguf",
        "params_b": 7.0,
        "quant": "Q4_K_M",
        "size_gb": 4.2,
        "min_ram_gb": 8,
        "rec_ram_gb": 14,
        "vision": True,
        "description": "Powerful vision-language model. Excellent at detecting IDs, credit cards, and documents in images.",
        "url": "https://huggingface.co/cjpais/llava-v1.6-mistral-7b-gguf",
        "download_url": "https://huggingface.co/cjpais/llava-v1.6-mistral-7b-gguf/resolve/main/llava-v1.6-mistral-7b-q4_k_m.gguf"
    },
    # --- Large / Power models (≥ 16 GB RAM) ---
    {
        "name": "Qwen2.5 14B",
        "filename": "qwen2.5-14b-instruct-q4_k_m.gguf",
        "params_b": 14.0,
        "quant": "Q4_K_M",
        "size_gb": 8.7,
        "min_ram_gb": 16,
        "rec_ram_gb": 24,
        "vision": False,
        "description": "High-accuracy text model for thorough PII analysis. Best precision on complex documents.",
        "url": "https://huggingface.co/Qwen/Qwen2.5-14B-Instruct-GGUF",
        "download_url": "https://huggingface.co/Qwen/Qwen2.5-14B-Instruct-GGUF/resolve/main/qwen2.5-14b-instruct-q4_k_m.gguf"
    },
    {
        "name": "Gemma 4 12B",
        "filename": "gemma-4-12b-it-q4_k_m.gguf",
        "params_b": 12.0,
        "quant": "Q4_K_M",
        "size_gb": 7.5,
        "min_ram_gb": 16,
        "rec_ram_gb": 24,
        "vision": True,
        "description": "Google's flagship multimodal model. Top-tier for both vision and text PII detection.",
        "url": "https://huggingface.co/google/gemma-4-12b-it",
        "download_url": "https://huggingface.co/google/gemma-4-12b-it/resolve/main/gemma-4-12b-it-q4_k_m.gguf"
    },
    {
        "name": "Mistral Small 24B",
        "filename": "mistral-small-24b-instruct-q4_k_m.gguf",
        "params_b": 24.0,
        "quant": "Q4_K_M",
        "size_gb": 14.0,
        "min_ram_gb": 24,
        "rec_ram_gb": 32,
        "vision": False,
        "description": "Enterprise-grade text analysis. Maximum accuracy for comprehensive data loss prevention.",
        "url": "https://huggingface.co/mistralai/Mistral-Small-24B-Instruct-2501",
        "download_url": "https://huggingface.co/mistralai/Mistral-Small-24B-Instruct-2501/resolve/main/mistral-small-24b-instruct-q4_k_m.gguf"
    },
]


# ---------------------------------------------------------------------------
# Hardware Detection
# ---------------------------------------------------------------------------

def get_cpu_info():
    """
    Returns a dict with cpu_name, cpu_cores (physical), and cpu_threads (logical).
    """
    cpu_name = platform.processor() or "Unknown CPU"
    cpu_threads = os.cpu_count() or 1

    # Try to get a better CPU brand string on Windows via WMI, or /proc/cpuinfo on Linux
    try:
        if sys.platform == "win32":
            out = subprocess.check_output(
                ["wmic", "cpu", "get", "name"],
                text=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            lines = [l.strip() for l in out.strip().splitlines() if l.strip() and l.strip().lower() != "name"]
            if lines:
                cpu_name = lines[0]
        elif sys.platform == "darwin":
            out = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True)
            cpu_name = out.strip() or cpu_name
        else:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if line.startswith("model name"):
                        cpu_name = line.split(":", 1)[1].strip()
                        break
    except Exception:
        pass

    # Physical cores — try to detect, fallback to threads // 2
    physical_cores = cpu_threads
    try:
        if sys.platform == "win32":
            out = subprocess.check_output(
                ["wmic", "cpu", "get", "NumberOfCores"],
                text=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            lines = [l.strip() for l in out.strip().splitlines() if l.strip() and l.strip().lower() != "numberofcores"]
            if lines:
                physical_cores = int(lines[0])
        elif sys.platform == "darwin":
            out = subprocess.check_output(["sysctl", "-n", "hw.physicalcpu"], text=True)
            physical_cores = int(out.strip())
        else:
            cores_set = set()
            with open("/proc/cpuinfo", "r") as f:
                current_physical = None
                for line in f:
                    if line.startswith("physical id"):
                        current_physical = line.split(":", 1)[1].strip()
                    elif line.startswith("core id") and current_physical is not None:
                        cores_set.add((current_physical, line.split(":", 1)[1].strip()))
            if cores_set:
                physical_cores = len(cores_set)
    except Exception:
        physical_cores = max(1, cpu_threads // 2)

    return {
        "cpu_name": cpu_name,
        "cpu_cores": physical_cores,
        "cpu_threads": cpu_threads,
    }


def get_gpu_info():
    """
    Detects NVIDIA GPU name and VRAM via nvidia-smi.
    Returns {"gpu_name": str|None, "gpu_vram_gb": float|None}.
    """
    try:
        flags = 0
        if sys.platform == "win32":
            flags = subprocess.CREATE_NO_WINDOW
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            text=True, creationflags=flags, timeout=5
        )
        line = out.strip().splitlines()[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2:
            gpu_name = parts[0]
            vram_mb = float(parts[1])
            return {"gpu_name": gpu_name, "gpu_vram_gb": round(vram_mb / 1024, 2)}
    except Exception:
        pass
    return {"gpu_name": None, "gpu_vram_gb": None}


def get_ram_info():
    """
    Returns {"ram_total_gb": float, "ram_available_gb": float}.
    Uses the existing get_system_ram() for total, plus available RAM detection.
    """
    try:
        from .scanner import get_system_ram
    except (ImportError, ValueError):
        from backend.scanner import get_system_ram
    total_bytes = get_system_ram()
    total_gb = round(total_bytes / (1024 ** 3), 2)

    available_gb = total_gb  # fallback
    try:
        if sys.platform == "win32":
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            available_gb = round(stat.ullAvailPhys / (1024 ** 3), 2)
        elif sys.platform == "darwin":
            # vm_stat gives pages, page size is typically 4096
            out = subprocess.check_output(["vm_stat"], text=True)
            free = 0
            for line in out.splitlines():
                if "free" in line.lower() or "inactive" in line.lower():
                    parts = line.split(":")
                    if len(parts) == 2:
                        val = parts[1].strip().rstrip(".")
                        try:
                            free += int(val) * 4096
                        except ValueError:
                            pass
            if free > 0:
                available_gb = round(free / (1024 ** 3), 2)
        else:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        available_gb = round(int(line.split()[1]) * 1024 / (1024 ** 3), 2)
                        break
    except Exception:
        pass

    return {"ram_total_gb": total_gb, "ram_available_gb": available_gb}


def get_full_system_specs():
    """
    Returns a comprehensive hardware profile dict with all detected specs.
    """
    ram = get_ram_info()
    cpu = get_cpu_info()
    gpu = get_gpu_info()

    return {
        "ram_total_gb": ram["ram_total_gb"],
        "ram_available_gb": ram["ram_available_gb"],
        "cpu_name": cpu["cpu_name"],
        "cpu_cores": cpu["cpu_cores"],
        "cpu_threads": cpu["cpu_threads"],
        "gpu_name": gpu["gpu_name"],
        "gpu_vram_gb": gpu["gpu_vram_gb"],
        "os_platform": sys.platform,
    }


# ---------------------------------------------------------------------------
# Model Recommendation Engine
# ---------------------------------------------------------------------------

def compute_fit_score(model, specs):
    """
    Computes a 0–100 fit score for a model given the system specs.
    Higher is better. Returns (score, tier_label).
    """
    total_ram = specs.get("ram_total_gb", 8)
    min_ram = model["min_ram_gb"]
    rec_ram = model["rec_ram_gb"]
    model_size = model["size_gb"]

    # Cannot run at all
    if total_ram < min_ram:
        return 0, "Too Large"

    # Headroom ratio: how much RAM is left after loading the model
    # Model in memory is roughly 1.1x file size for overhead
    estimated_mem = model_size * 1.2
    headroom = total_ram - estimated_mem

    if headroom <= 0:
        return 0, "Too Large"

    # Score based on how well the model fits
    # Perfect score if we have ≥ rec_ram
    if total_ram >= rec_ram:
        base_score = 85
        # Bonus for extra headroom beyond recommended
        extra = total_ram - rec_ram
        bonus = min(15, extra * 2)
        score = base_score + bonus
    elif total_ram >= min_ram:
        # Proportional score between min and rec
        progress = (total_ram - min_ram) / max(1, rec_ram - min_ram)
        score = 40 + progress * 45  # 40–85 range
    else:
        score = 0

    # GPU bonus: if we have a GPU, larger models get a slight boost
    gpu_vram = specs.get("gpu_vram_gb")
    if gpu_vram and gpu_vram > 2:
        # Models that fit in VRAM get a boost
        if model_size <= gpu_vram * 0.9:
            score = min(100, score + 5)

    score = max(0, min(100, round(score)))

    # Tier labels
    if score >= 80:
        tier = "Excellent"
    elif score >= 55:
        tier = "Good"
    elif score > 0:
        tier = "Tight"
    else:
        tier = "Too Large"

    return score, tier


def get_recommended_models(specs=None):
    """
    Returns the MODEL_CATALOG annotated with fit_score and fit_tier
    for the given (or auto-detected) system specs, sorted by fit_score descending.
    Models that are "Too Large" are included but sorted last.
    """
    if specs is None:
        specs = get_full_system_specs()

    results = []
    for model in MODEL_CATALOG:
        score, tier = compute_fit_score(model, specs)
        entry = dict(model)
        entry["fit_score"] = score
        entry["fit_tier"] = tier
        results.append(entry)

    # Sort: runnable models first (by score desc), then too-large models
    results.sort(key=lambda m: (-m["fit_score"], m["size_gb"]))
    return results
