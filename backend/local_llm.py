"""
Local GGUF model loader and inference wrapper for Argus PII Guard.

Provides model scanning, loading/unloading, and chat-completion inference
using llama-cpp-python as the backend, matching the Ollama response format
so the scanner can use it transparently.
"""

import os
import threading
from pathlib import Path


# Module-level state for the loaded model
_model_lock = threading.Lock()
_loaded_model = None
_loaded_model_path = None
_loaded_model_info = None


def is_available():
    """Check if llama-cpp-python is installed and importable."""
    try:
        import llama_cpp  # noqa: F401
        return True
    except ImportError:
        return False


def scan_models_folder(folder_path):
    """
    Scan a directory for .gguf model files.
    Returns a list of dicts with metadata about each discovered model.
    """
    models = []
    folder = Path(folder_path)

    if not folder.exists() or not folder.is_dir():
        return models

    for file_path in sorted(folder.iterdir()):
        if file_path.suffix.lower() == ".gguf" and file_path.is_file():
            size_bytes = file_path.stat().st_size
            size_gb = round(size_bytes / (1024 ** 3), 2)
            models.append({
                "filename": file_path.name,
                "path": str(file_path),
                "size_bytes": size_bytes,
                "size_gb": size_gb,
            })

    return models


def load_model(gguf_path, n_gpu_layers=0, n_ctx=2048):
    """
    Load a GGUF model from disk into memory.
    Returns True on success, raises on failure.
    Thread-safe via module lock.
    """
    global _loaded_model, _loaded_model_path, _loaded_model_info

    if not is_available():
        raise RuntimeError(
            "llama-cpp-python is not installed. "
            "Install it with: pip install llama-cpp-python"
        )

    path = Path(gguf_path)
    if not path.exists():
        raise FileNotFoundError(f"Model file not found: {gguf_path}")

    import llama_cpp

    with _model_lock:
        # Unload previous model if any
        if _loaded_model is not None:
            _unload_model_unsafe()

        model = llama_cpp.Llama(
            model_path=str(path),
            n_gpu_layers=n_gpu_layers,
            n_ctx=n_ctx,
            verbose=False,
        )

        _loaded_model = model
        _loaded_model_path = str(path)
        _loaded_model_info = {
            "filename": path.name,
            "path": str(path),
            "size_gb": round(path.stat().st_size / (1024 ** 3), 2),
            "n_gpu_layers": n_gpu_layers,
            "n_ctx": n_ctx,
            "status": "loaded",
        }

    return True


def _unload_model_unsafe():
    """Internal unload without lock — caller must hold _model_lock."""
    global _loaded_model, _loaded_model_path, _loaded_model_info
    if _loaded_model is not None:
        del _loaded_model
        _loaded_model = None
    _loaded_model_path = None
    _loaded_model_info = None


def unload_model():
    """Unload the currently loaded model and free memory. Thread-safe."""
    with _model_lock:
        _unload_model_unsafe()
    return True


def get_loaded_model_info():
    """
    Returns info dict about the currently loaded model, or None if no model is loaded.
    """
    with _model_lock:
        if _loaded_model_info is not None:
            return dict(_loaded_model_info)
        return None


def chat_completion(messages, temperature=0.0):
    """
    Run chat completion inference using the loaded GGUF model.

    Args:
        messages: List of dicts with 'role' and 'content' keys
                  (matching the Ollama/OpenAI chat format).
        temperature: Sampling temperature (0.0 = deterministic).

    Returns:
        A dict matching the Ollama client.chat() response format:
        {"message": {"role": "assistant", "content": "..."}}

    Raises:
        RuntimeError if no model is loaded.
    """
    with _model_lock:
        if _loaded_model is None:
            raise RuntimeError("No GGUF model is currently loaded. Load a model first.")

        # llama-cpp-python uses create_chat_completion which expects
        # messages in OpenAI format: [{"role": "...", "content": "..."}]
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        response = _loaded_model.create_chat_completion(
            messages=formatted_messages,
            temperature=temperature,
            max_tokens=1024,
        )

        # Extract the assistant's response text
        content = ""
        if response and "choices" in response and len(response["choices"]) > 0:
            content = response["choices"][0].get("message", {}).get("content", "")

        # Return in Ollama-compatible format
        return {
            "message": {
                "role": "assistant",
                "content": content,
            }
        }
