"""
Main backend orchestrator and PyWebView JS API interface for Argus PII Guard.

Provides:
- PyWebView JavaScript bridge (`Api` class) with typed endpoints for UI interaction.
- Asynchronous scan progress telemetry and background scheduler loop.
- Unified multimedia preview generation (image, document, plain text).
- Native application lifecycle and window initialization.
"""

import base64
import ctypes
import io
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional, Union

import webview
from PIL import Image

# Ensure package context when main.py is executed directly (e.g. PyInstaller entry script)
if __package__ is None or __package__ == "":
    file_path = Path(__file__).resolve()
    parent_dir = str(file_path.parent.parent)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    __package__ = "backend"

try:
    from . import installer, local_llm, model_downloader, remediation
    from .hardware_info import get_full_system_specs, get_recommended_models
    from .scanner import (
        calculate_file_checksum,
        ensure_ollama_running,
        get_auto_config,
        get_system_ram,
        scan_state,
        start_scan_thread,
        state_lock,
        stop_scan,
    )
    from .state import load_results, load_settings, save_results, save_settings
except (ImportError, ValueError):
    import backend.installer as installer
    import backend.local_llm as local_llm
    import backend.model_downloader as model_downloader
    import backend.remediation as remediation
    from backend.hardware_info import get_full_system_specs, get_recommended_models
    from backend.scanner import (
        calculate_file_checksum,
        ensure_ollama_running,
        get_auto_config,
        get_system_ram,
        scan_state,
        start_scan_thread,
        state_lock,
        stop_scan,
    )
    from backend.state import load_results, load_settings, save_results, save_settings


def _encode_image_to_data_uri(file_path: str, ext: str) -> str:
    """Encodes an image file to a base64 data URI string (converting HEIC to JPEG)."""
    if ext in {".heic", ".heif"}:
        with Image.open(file_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG")
            encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
            return f"data:image/jpeg;base64,{encoded}"

    mime = "image/png" if ext == ".png" else "image/webp" if ext == ".webp" else "image/bmp" if ext == ".bmp" else "image/jpeg"
    with open(file_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime};base64,{encoded}"


class Api:
    """
    Exposes Python backend methods to the frontend JavaScript runtime via pywebview.
    """

    def __init__(self) -> None:
        self._window: Optional[Any] = None

    def set_window(self, window: Any) -> None:
        """Sets the active pywebview window instance."""
        self._window = window

    # ------------------------------------------------------------------
    # System & Settings
    # ------------------------------------------------------------------

    def get_system_info(self) -> dict[str, Any]:
        """Returns physical RAM and recommended system concurrency configuration."""
        try:
            ram_bytes = get_system_ram()
            ram_gb = round(ram_bytes / (1024 ** 3), 2)
            auto_cfg = get_auto_config(ram_bytes)
            return {
                "ram_gb": ram_gb,
                "recommended_concurrency": auto_cfg["concurrency"],
                "recommended_image_opt": auto_cfg["image_optimization"],
                "recommended_text_mode": auto_cfg["text_scan_mode"],
            }
        except Exception as e:
            return {"error": str(e)}

    def get_settings(self) -> dict[str, Any]:
        """Returns loaded application settings."""
        return load_settings()

    def save_settings(self, settings_dict: dict[str, Any]) -> bool:
        """Persists updated application settings to disk."""
        save_settings(settings_dict)
        return True

    def get_results(self) -> list[dict[str, Any]]:
        """Returns saved scan findings."""
        return load_results()

    def save_results(self, results: list[dict[str, Any]]) -> bool:
        """Persists scan findings to disk."""
        save_results(results)
        return True

    def select_folder(self) -> list[str]:
        """Opens native directory picker dialog, returning selected paths."""
        if self._window:
            result = self._window.create_file_dialog(
                webview.FileDialog.FOLDER, allow_multiple=True
            )
            return result if result else []
        return []

    def check_ollama(self) -> dict[str, Any]:
        """Checks if the Ollama inference backend is running."""
        success, msg = ensure_ollama_running()
        return {"success": success, "message": msg}

    # ------------------------------------------------------------------
    # Scanner Operations
    # ------------------------------------------------------------------

    def start_scan(self, rescan_all: bool = False) -> dict[str, Any]:
        """Validates target folders and launches the background scan worker."""
        settings = load_settings()
        folders = settings.get("folders", [])
        if not folders:
            return {
                "success": False,
                "error": "no_directories",
                "message": "Please add at least one directory to inspect first.",
            }

        valid_folders = [f for f in folders if f and isinstance(f, str) and os.path.exists(f)]
        if not valid_folders:
            return {
                "success": False,
                "error": "invalid_directories",
                "message": "The configured target directories could not be found on disk. Please verify or re-add them.",
            }

        started = start_scan_thread(valid_folders, save_results, rescan_all)
        if started:
            return {"success": True}
        return {
            "success": False,
            "error": "scan_in_progress",
            "message": "A scan is already in progress or currently terminating. Please wait a moment and try again.",
        }

    def stop_scan(self) -> dict[str, bool]:
        """Requests graceful termination of active scan thread."""
        stop_scan(timeout=2.0)
        return {"success": True}

    def get_scan_progress(self) -> dict[str, Any]:
        """Returns current scanning telemetry and findings."""
        return {
            "is_scanning": scan_state.is_scanning,
            "progress": scan_state.progress,
            "flagged_files": scan_state.flagged_files,
        }

    def delete_files(self, file_paths: list[str]) -> list[str]:
        """Permanently deletes multiple files, updating state and results."""
        deleted: list[str] = []
        for path in file_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
                    deleted.append(path)
            except Exception as e:
                print(f"Failed to delete {path}: {e}")

        # Update saved results
        results = [r for r in load_results() if r["file"] not in deleted]
        save_results(results)

        # Update live scan state
        with state_lock:
            scan_state.flagged_files = [f for f in scan_state.flagged_files if f["file"] not in deleted]
            scan_state.progress["flagged_count"] = len(scan_state.flagged_files)

        return deleted

    def verify_file(self, file_path: str) -> dict[str, Any]:
        """Triggers on-demand LLM verification for a regex-flagged text file."""
        from .scanner import verify_text_file_with_ai
        result = verify_text_file_with_ai(file_path)

        if not result.get("compromised"):
            from .state import load_cache, save_cache
            cache = load_cache()
            str_path = str(file_path)
            try:
                stat = os.stat(str_path)
                mtime, size = stat.st_mtime, stat.st_size
            except OSError:
                mtime, size = 0, 0
            checksum = calculate_file_checksum(str_path)
            cache[str_path] = {
                "mtime": mtime,
                "size": size,
                "checksum": checksum,
                "result": result,
            }
            save_cache(cache)

        results = load_results()
        for r in list(results):
            if r.get("file") == file_path:
                if result.get("compromised"):
                    r["needs_ai_verification"] = False
                    r["reason"] = result.get("reason")
                    r["verified_true"] = True
                    r["compromised"] = True
                    r["snippets"] = result.get("snippets", [])
                    r["items"] = result.get("items", [])
                else:
                    results.remove(r)
                break
        save_results(results)

        with state_lock:
            for f in list(scan_state.flagged_files):
                if f.get("file") == file_path:
                    if result.get("compromised"):
                        f["needs_ai_verification"] = False
                        f["reason"] = result.get("reason")
                        f["verified_true"] = True
                        f["compromised"] = True
                        f["snippets"] = result.get("snippets", [])
                        f["items"] = result.get("items", [])
                    else:
                        scan_state.flagged_files.remove(f)
                        scan_state.progress["flagged_count"] = len(scan_state.flagged_files)
                    break

        return {"success": True, "result": result}

    def mark_files_ok(self, file_paths: list[str]) -> dict[str, Any]:
        """Marks multiple files as safe, caching benign status and clearing findings."""
        from .state import load_cache, save_cache
        cache = load_cache()
        for path in file_paths:
            str_path = str(path)
            try:
                stat = os.stat(str_path)
                mtime, size = stat.st_mtime, stat.st_size
            except OSError:
                mtime, size = 0, 0
            checksum = calculate_file_checksum(str_path)
            cache[str_path] = {
                "mtime": mtime,
                "size": size,
                "checksum": checksum,
                "result": {"compromised": False, "marked_ok": True, "reason": "Marked as OK by user"},
            }
        save_cache(cache)

        new_results = [r for r in load_results() if r.get("file") not in file_paths]
        save_results(new_results)

        with state_lock:
            scan_state.flagged_files = [f for f in scan_state.flagged_files if f.get("file") not in file_paths]
            scan_state.progress["flagged_count"] = len(scan_state.flagged_files)

        return {"success": True, "cleared": file_paths}

    def mark_file_ok(self, file_path: str) -> dict[str, Any]:
        """Marks a single file as safe."""
        return self.mark_files_ok([file_path])

    # ------------------------------------------------------------------
    # File Inspection & Preview API
    # ------------------------------------------------------------------

    def get_file_preview_details(self, file_path: str) -> dict[str, Any]:
        """Generates rich file preview metadata, extracted content, annotations, and checksums."""
        try:
            if not os.path.exists(file_path):
                return {"error": "File not found on disk"}

            ext = os.path.splitext(file_path)[1].lower()
            saved_results = load_results()
            file_record = next((r for r in saved_results if r.get("file") == file_path), None)
            reason = file_record.get("reason") if file_record else None
            saved_items = file_record.get("items", []) if file_record else []
            saved_snippets = file_record.get("snippets", []) if file_record else []

            from .scanner import HEIC_EXTENSIONS, IMAGE_EXTENSIONS, OFFICE_EXTENSIONS, PDF_EXTENSIONS
            checksum = (file_record.get("checksum") if file_record and file_record.get("checksum") else calculate_file_checksum(file_path))
            is_writable = remediation.check_write_permission(file_path)

            if ext in IMAGE_EXTENSIONS or ext in HEIC_EXTENSIONS:
                try:
                    data_uri = _encode_image_to_data_uri(file_path, ext)
                except Exception as e:
                    return {"error": f"Error decoding image: {str(e)}"}

                return {
                    "file_path": file_path,
                    "file_name": os.path.basename(file_path),
                    "file_type": "HEIC" if ext in HEIC_EXTENSIONS else "Image",
                    "content_type": "image",
                    "data": data_uri,
                    "items": saved_items,
                    "reason": reason or "Image inspected for sensitive content",
                    "checksum": checksum,
                    "is_writable": is_writable,
                }
            else:
                from .scanner import get_file_text_content, locate_text_pii_matches
                content = get_file_text_content(Path(file_path))
                if not content:
                    content = "(No readable text could be extracted or file is empty)"
                    highlights = []
                else:
                    highlights = locate_text_pii_matches(content, ai_snippets=saved_snippets, file_path=file_path)

                doc_type = "PDF" if ext in PDF_EXTENSIONS else "Office" if ext in OFFICE_EXTENSIONS else "Text"
                return {
                    "file_path": file_path,
                    "file_name": os.path.basename(file_path),
                    "file_type": doc_type,
                    "content_type": "text",
                    "content": content,
                    "highlights": highlights,
                    "reason": reason or (f"Flagged with {len(highlights)} PII findings" if highlights else "No PII matches detected"),
                    "checksum": checksum,
                    "is_writable": is_writable,
                }
        except Exception as e:
            return {"error": f"Preview error: {str(e)}"}

    def get_image_base64(self, file_path: str) -> Optional[str]:
        """Legacy helper for image previews."""
        if not os.path.exists(file_path):
            return None
        ext = os.path.splitext(file_path)[1].lower()
        if ext in {".heic", ".heif"}:
            return "HEIC_FORMAT"
        preview = self.get_file_preview_details(file_path)
        if "error" in preview:
            return f"Preview error: {preview['error']}"
        if preview.get("content_type") == "image":
            return preview.get("data")
        return preview.get("content", "")

    # ------------------------------------------------------------------
    # Remediation & Cleansing API
    # ------------------------------------------------------------------

    def redact_entity(
        self,
        file_path: str,
        line_number: int = 1,
        start_col: int = 0,
        end_col: int = 0,
        match_text: str = "",
        mask_pattern: Optional[str] = None,
        expected_checksum: Optional[str] = None,
    ) -> dict[str, Any]:
        """Sanitizes an individual detected PII finding in-place."""
        try:
            if mask_pattern is None:
                mask_pattern = load_settings().get("redaction_mask_pattern", "redacted")
            return remediation.redact_file_entity(
                file_path=file_path,
                line_number=line_number,
                start_col=start_col,
                end_col=end_col,
                match_text=match_text,
                mask_pattern=mask_pattern,
                expected_checksum=expected_checksum,
            )
        except Exception as e:
            return {"success": False, "error": str(e), "message": str(e)}

    def batch_redact(
        self,
        file_path: str,
        mask_pattern: Optional[str] = None,
        expected_checksum: Optional[str] = None,
    ) -> dict[str, Any]:
        """Sanitizes all detected PII findings in a file in a single atomic pass."""
        try:
            if mask_pattern is None:
                mask_pattern = load_settings().get("redaction_mask_pattern", "redacted")
            return remediation.batch_redact_file(
                file_path=file_path,
                mask_pattern=mask_pattern,
                expected_checksum=expected_checksum,
            )
        except Exception as e:
            return {"success": False, "error": str(e), "message": str(e)}

    def delete_file_item(self, file_path: str, permanent: Optional[bool] = None) -> dict[str, Any]:
        """Deletes a file (moves to Recycle Bin/Trash by default, or permanently)."""
        try:
            if permanent is None:
                permanent = (load_settings().get("deletion_mode", "trash") == "permanent")
            return remediation.trash_or_delete_file(file_path, permanent=permanent)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def batch_delete_files(self, file_paths: list[str], permanent: Optional[bool] = None) -> list[str]:
        """Deletes multiple files, returning list of successfully removed items."""
        deleted: list[str] = []
        if permanent is None:
            permanent = (load_settings().get("deletion_mode", "trash") == "permanent")
        for path in file_paths:
            res = remediation.trash_or_delete_file(path, permanent=permanent)
            if res.get("success"):
                deleted.append(path)
        return deleted

    def mark_as_safe(
        self,
        file_path: str,
        match_text: Optional[str] = None,
        pattern_name: Optional[str] = None,
        reason: str = "Whitelisted by user",
    ) -> dict[str, Any]:
        """Whitelists a file or specific entity exception and updates .argusignore."""
        try:
            return remediation.mark_as_safe_exception(
                file_path=file_path,
                match_text=match_text,
                pattern_name=pattern_name,
                reason=reason,
            )
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_allowed_exceptions(self) -> list[dict[str, Any]]:
        """Returns list of all active whitelisted exceptions."""
        try:
            return remediation.get_allowed_exceptions()
        except Exception as e:
            return {"error": str(e)}  # type: ignore[return-value]

    def remove_allowed_exception(self, exception_id: str) -> dict[str, Any]:
        """Removes a whitelisted exception by ID."""
        try:
            return remediation.remove_allowed_exception(exception_id)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def fix_file_permissions(self, file_path: str) -> dict[str, Any]:
        """Removes read-only attributes from a file."""
        try:
            return remediation.fix_file_permissions(file_path)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_backups_list(self) -> list[dict[str, Any]]:
        """Returns list of created backup snapshots in .argus_backups/."""
        try:
            return remediation.list_backups()
        except Exception as e:
            return {"error": str(e)}  # type: ignore[return-value]

    def restore_backup_file(self, backup_id_or_path: str) -> dict[str, Any]:
        """Restores an original file from its backup snapshot."""
        try:
            return remediation.restore_backup(backup_id_or_path)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def prune_backups(self, max_days: int = 7) -> dict[str, Any]:
        """Prunes expired backups older than max_days."""
        try:
            count = remediation.prune_expired_backups(max_days=max_days)
            return {"success": True, "pruned_count": count}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Hardware & Local Model Management API
    # ------------------------------------------------------------------

    def get_hardware_specs(self) -> dict[str, Any]:
        """Returns comprehensive system hardware profile."""
        try:
            return get_full_system_specs()
        except Exception as e:
            return {"error": str(e)}

    def get_recommended_models(self) -> dict[str, Any]:
        """Returns the curated model catalog ranked by hardware fit."""
        try:
            specs = get_full_system_specs()
            models = get_recommended_models(specs)
            return {"specs": specs, "models": models}
        except Exception as e:
            return {"error": str(e)}

    def select_models_folder(self) -> Optional[str]:
        """Opens native folder picker for local GGUF models."""
        if self._window:
            result = self._window.create_file_dialog(
                webview.FileDialog.FOLDER, allow_multiple=False
            )
            if result and len(result) > 0:
                folder_path = result[0]
                settings = load_settings()
                settings["models_folder"] = folder_path
                save_settings(settings)
                return folder_path
        return None

    def scan_models_folder(self, folder_path: Optional[str] = None) -> dict[str, Any]:
        """Scans folder for .gguf model files."""
        try:
            if not folder_path:
                folder_path = load_settings().get("models_folder", "")
            if not folder_path:
                return {"error": "No models folder configured"}
            models = local_llm.scan_models_folder(folder_path)
            return {"folder": folder_path, "models": models}
        except Exception as e:
            return {"error": str(e)}

    def load_local_model(self, model_path: str, n_gpu_layers: int = 0) -> dict[str, Any]:
        """Loads a specific .gguf model into memory."""
        try:
            if not local_llm.is_available():
                return {
                    "success": False,
                    "error": "llama-cpp-python is not installed. Install with: pip install llama-cpp-python",
                }
            local_llm.load_model(model_path, n_gpu_layers=n_gpu_layers)
            return {"success": True, "info": local_llm.get_loaded_model_info()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def unload_local_model(self) -> dict[str, Any]:
        """Unloads currently active GGUF model and frees memory."""
        try:
            local_llm.unload_model()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_loaded_model_info(self) -> Optional[dict[str, Any]]:
        """Returns metadata for loaded local model or None if idle."""
        return local_llm.get_loaded_model_info()

    def download_recommended_model(self, filename: str, download_url: str) -> dict[str, Any]:
        """Starts streaming download of a model from HuggingFace to the models directory."""
        try:
            folder_path = load_settings().get("models_folder", "")
            if not folder_path:
                return {"success": False, "prompt_folder": True, "error": "No models folder configured."}

            success, message = model_downloader.start_download(download_url, folder_path, filename)
            return {"success": success, "message": message, "filename": filename}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def cancel_model_download(self) -> dict[str, Any]:
        """Cancels active model download."""
        try:
            success, message = model_downloader.cancel_download()
            return {"success": success, "message": message}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_model_download_status(self) -> dict[str, Any]:
        """Returns model download progress and speed telemetry."""
        return model_downloader.get_download_status()

    # ------------------------------------------------------------------
    # Native Installer & Integration API
    # ------------------------------------------------------------------

    def get_installation_status(self, user_scope: bool = False) -> dict[str, Any]:
        """Returns installation presence, path, and manifest metadata."""
        default_path = installer.get_default_install_path(user_scope)
        priv_check = installer.check_privileges(default_path)
        manifest_path = default_path / "install_manifest.json"
        is_installed = manifest_path.exists()

        manifest_info = {}
        if is_installed:
            try:
                manifest_info = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        return {
            "is_installed": is_installed,
            "default_path": str(default_path),
            "privileges": priv_check,
            "manifest": manifest_info,
        }

    def install_app(
        self,
        source_dir: Optional[str] = None,
        target_dir: Optional[str] = None,
        user_scope: bool = False,
        add_to_path: bool = True,
    ) -> dict[str, Any]:
        """Triggers native desktop installation and integration."""
        try:
            engine = installer.InstallerEngine(source_dir=source_dir, target_dir=target_dir, user_scope=user_scope)
            return engine.install(add_to_path=add_to_path)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def uninstall_app(self, install_dir: Optional[str] = None) -> dict[str, Any]:
        """Triggers clean uninstallation and shortcut removal."""
        try:
            engine = installer.UninstallerEngine(install_dir=install_dir)
            return engine.uninstall()
        except Exception as e:
            return {"success": False, "error": str(e)}


def get_resource_path(relative_path: str) -> str:
    """
    Returns absolute path to resource, compatible with dev mode and PyInstaller frozen builds.
    """
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", relative_path))


def schedule_loop() -> None:
    """Background thread checking periodic scan schedule."""
    while True:
        settings = load_settings()
        if settings.get("schedule", {}).get("enabled"):
            target_time = settings["schedule"]["time"]
            current_time = time.strftime("%H:%M")
            if current_time == target_time and not scan_state.is_scanning:
                print("Starting scheduled scan...")
                start_scan_thread(settings["folders"], save_results)
                time.sleep(61)
                continue
        time.sleep(30)


def main() -> None:
    """Application entry point."""
    api = Api()

    scheduler = threading.Thread(target=schedule_loop, daemon=True)
    scheduler.start()

    frontend_path = get_resource_path(os.path.join("frontend", "index.html"))
    window = webview.create_window(
        "Argus PII Guard",
        url=frontend_path,
        js_api=api,
        width=1040,
        height=720,
        min_size=(850, 600),
    )
    api.set_window(window)

    icon_path = get_resource_path(os.path.join("frontend", "assets", "argus-icon.ico"))
    if not os.path.exists(icon_path):
        icon_path = get_resource_path(os.path.join("frontend", "assets", "argus-icon.png"))

    webview.start(debug=False, icon=icon_path if os.path.exists(icon_path) else None)


if __name__ == "__main__":
    main()
