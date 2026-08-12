import webview
import os
import sys
import ctypes
import base64
import threading
import time
from pathlib import Path

# Ensure package context when main.py is executed directly (e.g. PyInstaller entry script)
if __package__ is None or __package__ == "":
    file_path = Path(__file__).resolve()
    parent_dir = str(file_path.parent.parent)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    __package__ = "backend"

try:
    from .state import load_settings, save_settings, load_results, save_results
    from .scanner import start_scan_thread, stop_scan, scan_state, ensure_ollama_running, get_system_ram, get_auto_config
    from .hardware_info import get_full_system_specs, get_recommended_models
    from . import local_llm
    from . import model_downloader
    from . import remediation
except (ImportError, ValueError):
    from backend.state import load_settings, save_settings, load_results, save_results
    from backend.scanner import start_scan_thread, stop_scan, scan_state, ensure_ollama_running, get_system_ram, get_auto_config
    from backend.hardware_info import get_full_system_specs, get_recommended_models
    import backend.local_llm as local_llm
    import backend.model_downloader as model_downloader
    import backend.remediation as remediation

import io
from PIL import Image

class Api:
    def __init__(self):
        self._window = None

    def set_window(self, window):
        self._window = window

    def get_system_info(self):
        try:
            ram_bytes = get_system_ram()
            ram_gb = round(ram_bytes / (1024 ** 3), 2)
            auto_cfg = get_auto_config(ram_bytes)
            return {
                "ram_gb": ram_gb,
                "recommended_concurrency": auto_cfg["concurrency"],
                "recommended_image_opt": auto_cfg["image_optimization"],
                "recommended_text_mode": auto_cfg["text_scan_mode"]
            }
        except Exception as e:
            return {"error": str(e)}

    def get_settings(self):
        return load_settings()

    def save_settings(self, settings_dict):
        save_settings(settings_dict)
        return True

    def get_results(self):
        return load_results()

    def save_results(self, results):
        save_results(results)
        return True

    def select_folder(self):
        if self._window:
            result = self._window.create_file_dialog(
                webview.FileDialog.FOLDER, allow_multiple=True
            )
            return result if result else []
        return []

    def check_ollama(self):
        success, msg = ensure_ollama_running()
        return {"success": success, "message": msg}

    def start_scan(self, rescan_all=False):
        settings = load_settings()
        folders = settings.get("folders", [])
        if not folders or len(folders) == 0:
            return {
                "success": False,
                "error": "no_directories",
                "message": "Please add at least one directory to inspect first."
            }

        valid_folders = [f for f in folders if f and isinstance(f, str) and os.path.exists(f)]
        if not valid_folders:
            return {
                "success": False,
                "error": "invalid_directories",
                "message": "The configured target directories could not be found on disk. Please verify or re-add them."
            }

        # Save results callback
        def on_scan_complete(results):
            save_results(results)

        started = start_scan_thread(valid_folders, on_scan_complete, rescan_all)
        if started:
            return {"success": True}
        else:
            return {
                "success": False,
                "error": "scan_in_progress",
                "message": "A scan is already in progress or currently terminating. Please wait a moment and try again."
            }

    def stop_scan(self):
        stop_scan(timeout=2.0)
        return {"success": True}

    def get_scan_progress(self):
        return {
            "is_scanning": scan_state.is_scanning,
            "progress": scan_state.progress,
            "flagged_files": scan_state.flagged_files
        }

    def delete_files(self, file_paths):
        deleted = []
        for path in file_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
                    deleted.append(path)
            except Exception as e:
                print(f"Failed to delete {path}: {e}")
        
        # Update persistent results
        results = load_results()
        new_results = [r for r in results if r["file"] not in deleted]
        save_results(new_results)
        
        # Update live scan state
        from .scanner import state_lock
        with state_lock:
            scan_state.flagged_files = [f for f in scan_state.flagged_files if f["file"] not in deleted]
            scan_state.progress["flagged_count"] = len(scan_state.flagged_files)
        
        return deleted

    def verify_file(self, file_path):
        from .scanner import verify_text_file_with_ai
        result = verify_text_file_with_ai(file_path)
        
        if not result.get("compromised"):
            from .state import load_cache, save_cache
            from .scanner import calculate_file_checksum
            cache = load_cache()
            str_path = str(file_path)
            try:
                stat = os.stat(str_path)
                mtime = stat.st_mtime
                size = stat.st_size
            except:
                mtime = 0
                size = 0
            checksum = calculate_file_checksum(str_path)
            cache[str_path] = {
                "mtime": mtime,
                "size": size,
                "checksum": checksum,
                "result": result
            }
            save_cache(cache)
        
        results = load_results()
        for r in results:
            if r["file"] == file_path:
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
        
        from .scanner import state_lock
        with state_lock:
            for f in scan_state.flagged_files:
                if f["file"] == file_path:
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

    def mark_files_ok(self, file_paths):
        from .state import load_cache, save_cache
        from .scanner import calculate_file_checksum
        cache = load_cache()
        for path in file_paths:
            str_path = str(path)
            try:
                stat = os.stat(str_path)
                mtime = stat.st_mtime
                size = stat.st_size
            except:
                mtime = 0
                size = 0
            checksum = calculate_file_checksum(str_path)
            cache[str_path] = {
                "mtime": mtime,
                "size": size,
                "checksum": checksum,
                "result": {"compromised": False, "marked_ok": True, "reason": "Marked as OK by user"}
            }
        save_cache(cache)

        # Update persistent results
        results = load_results()
        new_results = [r for r in results if r["file"] not in file_paths]
        save_results(new_results)

        # Update live scan state
        from .scanner import state_lock
        with state_lock:
            scan_state.flagged_files = [f for f in scan_state.flagged_files if f["file"] not in file_paths]
            scan_state.progress["flagged_count"] = len(scan_state.flagged_files)

        return {"success": True, "cleared": file_paths}

    def mark_file_ok(self, file_path):
        return self.mark_files_ok([file_path])

    def get_file_preview_details(self, file_path):
        try:
            if not os.path.exists(file_path):
                return {"error": "File not found on disk"}
            
            ext = os.path.splitext(file_path)[1].lower()
            
            saved_results = load_results()
            file_record = next((r for r in saved_results if r.get("file") == file_path), None)
            reason = file_record.get("reason") if file_record else None
            saved_items = file_record.get("items", []) if file_record else []
            saved_snippets = file_record.get("snippets", []) if file_record else []

            from .scanner import IMAGE_EXTENSIONS, HEIC_EXTENSIONS, PDF_EXTENSIONS, OFFICE_EXTENSIONS, calculate_file_checksum
            checksum = file_record.get("checksum") if file_record and file_record.get("checksum") else calculate_file_checksum(file_path)

            is_writable = remediation.check_write_permission(file_path)

            if ext in IMAGE_EXTENSIONS or ext in HEIC_EXTENSIONS:
                if ext in HEIC_EXTENSIONS:
                    try:
                        with Image.open(file_path) as img:
                            if img.mode in ("RGBA", "P"):
                                img = img.convert("RGB")
                            buf = io.BytesIO()
                            img.save(buf, format="JPEG")
                            encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
                            data_uri = f"data:image/jpeg;base64,{encoded}"
                    except Exception as e:
                        return {"error": f"Error decoding HEIC image: {str(e)}"}
                else:
                    mime = "image/png" if ext == ".png" else "image/webp" if ext == ".webp" else "image/bmp" if ext == ".bmp" else "image/jpeg"
                    with open(file_path, "rb") as f:
                        encoded = base64.b64encode(f.read()).decode("utf-8")
                        data_uri = f"data:{mime};base64,{encoded}"

                return {
                    "file_path": file_path,
                    "file_name": os.path.basename(file_path),
                    "file_type": "HEIC" if ext in HEIC_EXTENSIONS else "Image",
                    "content_type": "image",
                    "data": data_uri,
                    "items": saved_items,
                    "reason": reason or "Image inspected for sensitive content",
                    "checksum": checksum,
                    "is_writable": is_writable
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
                    "is_writable": is_writable
                }
        except Exception as e:
            return {"error": f"Preview error: {str(e)}"}

    def get_image_base64(self, file_path):
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

    def redact_entity(self, file_path, line_number=1, start_col=0, end_col=0, match_text="", mask_pattern=None, expected_checksum=None):
        """Sanitizes an individual PII match in-place."""
        try:
            if mask_pattern is None:
                settings = load_settings()
                mask_pattern = settings.get("redaction_mask_pattern", "redacted")
            return remediation.redact_file_entity(
                file_path=file_path,
                line_number=line_number,
                start_col=start_col,
                end_col=end_col,
                match_text=match_text,
                mask_pattern=mask_pattern,
                expected_checksum=expected_checksum
            )
        except Exception as e:
            return {"success": False, "error": str(e), "message": str(e)}

    def batch_redact(self, file_path, mask_pattern=None, expected_checksum=None):
        """Sanitizes all detected PII matches in a file in a single atomic pass."""
        try:
            if mask_pattern is None:
                settings = load_settings()
                mask_pattern = settings.get("redaction_mask_pattern", "redacted")
            return remediation.batch_redact_file(
                file_path=file_path,
                mask_pattern=mask_pattern,
                expected_checksum=expected_checksum
            )
        except Exception as e:
            return {"success": False, "error": str(e), "message": str(e)}

    def delete_file_item(self, file_path, permanent=None):
        """Deletes a file (moves to Recycle Bin/Trash by default, or permanent)."""
        try:
            if permanent is None:
                settings = load_settings()
                permanent = (settings.get("deletion_mode", "trash") == "permanent")
            return remediation.trash_or_delete_file(file_path, permanent=permanent)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def batch_delete_files(self, file_paths, permanent=None):
        """Deletes multiple files, returning list of successfully removed items."""
        deleted = []
        if permanent is None:
            settings = load_settings()
            permanent = (settings.get("deletion_mode", "trash") == "permanent")
        for path in file_paths:
            res = remediation.trash_or_delete_file(path, permanent=permanent)
            if res.get("success"):
                deleted.append(path)
        return deleted

    def mark_as_safe(self, file_path, match_text=None, pattern_name=None, reason="Whitelisted by user"):
        """Whitelists a file or specific entity exception and updates .argusignore."""
        try:
            return remediation.mark_as_safe_exception(
                file_path=file_path,
                match_text=match_text,
                pattern_name=pattern_name,
                reason=reason
            )
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_allowed_exceptions(self):
        """Return list of whitelisted exceptions."""
        try:
            return remediation.get_allowed_exceptions()
        except Exception as e:
            return {"error": str(e)}

    def remove_allowed_exception(self, exception_id):
        """Remove an exception by ID."""
        try:
            return remediation.remove_allowed_exception(exception_id)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def fix_file_permissions(self, file_path):
        """Removes read-only attributes from file."""
        try:
            return remediation.fix_file_permissions(file_path)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_backups_list(self):
        """Return list of created backups in .argus_backups/."""
        try:
            return remediation.list_backups()
        except Exception as e:
            return {"error": str(e)}

    def restore_backup_file(self, backup_id_or_path):
        """Restore file from a backup."""
        try:
            return remediation.restore_backup(backup_id_or_path)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def prune_backups(self, max_days=7):
        """Prunes expired backups older than max_days."""
        try:
            count = remediation.prune_expired_backups(max_days=max_days)
            return {"success": True, "pruned_count": count}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Hardware & Local Model Management API
    # ------------------------------------------------------------------

    def get_hardware_specs(self):
        """Return comprehensive hardware profile for the UI."""
        try:
            return get_full_system_specs()
        except Exception as e:
            return {"error": str(e)}

    def get_recommended_models(self):
        """Return the curated model catalog ranked by hardware fit."""
        try:
            specs = get_full_system_specs()
            models = get_recommended_models(specs)
            return {"specs": specs, "models": models}
        except Exception as e:
            return {"error": str(e)}

    def select_models_folder(self):
        """Open a native folder picker for the models directory."""
        if self._window:
            result = self._window.create_file_dialog(
                webview.FileDialog.FOLDER, allow_multiple=False
            )
            if result and len(result) > 0:
                folder_path = result[0]
                # Save to settings immediately
                settings = load_settings()
                settings["models_folder"] = folder_path
                save_settings(settings)
                return folder_path
        return None

    def scan_models_folder(self, folder_path=None):
        """Scan a folder for .gguf model files. Uses settings folder if none given."""
        try:
            if not folder_path:
                settings = load_settings()
                folder_path = settings.get("models_folder", "")
            if not folder_path:
                return {"error": "No models folder configured"}
            models = local_llm.scan_models_folder(folder_path)
            return {"folder": folder_path, "models": models}
        except Exception as e:
            return {"error": str(e)}

    def load_local_model(self, model_path, n_gpu_layers=0):
        """Load a specific .gguf model file."""
        try:
            if not local_llm.is_available():
                return {
                    "success": False,
                    "error": "llama-cpp-python is not installed. Install with: pip install llama-cpp-python"
                }
            local_llm.load_model(model_path, n_gpu_layers=n_gpu_layers)
            return {"success": True, "info": local_llm.get_loaded_model_info()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def unload_local_model(self):
        """Unload the currently loaded local model."""
        try:
            local_llm.unload_model()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_loaded_model_info(self):
        """Return info about the currently loaded local model (or null)."""
        return local_llm.get_loaded_model_info()

    def download_recommended_model(self, filename, download_url):
        """
        Download a recommended model file to the models folder.
        If no models folder is configured, returns prompt_folder=True.
        """
        try:
            settings = load_settings()
            folder_path = settings.get("models_folder", "")
            if not folder_path:
                return {"success": False, "prompt_folder": True, "error": "No models folder configured."}
            
            success, message = model_downloader.start_download(download_url, folder_path, filename)
            return {"success": success, "message": message, "filename": filename}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def cancel_model_download(self):
        """Cancel active model download if any."""
        try:
            success, message = model_downloader.cancel_download()
            return {"success": success, "message": message}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_model_download_status(self):
        """Return download status telemetry dict."""
        return model_downloader.get_download_status()

def get_resource_path(relative_path):
    """
    Get absolute path to resource, works for dev and for PyInstaller frozen build.
    """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", relative_path))

def schedule_loop():
    while True:
        settings = load_settings()
        if settings.get("schedule", {}).get("enabled"):
            target_time = settings["schedule"]["time"]
            current_time = time.strftime("%H:%M")
            if current_time == target_time and not scan_state.is_scanning:
                print("Starting scheduled scan...")
                start_scan_thread(settings["folders"], lambda res: save_results(res))
                # Sleep for 61 seconds to avoid triggering again in the same minute
                time.sleep(61)
                continue
        time.sleep(30)

def main():
    api = Api()
    
    # Start scheduler thread
    scheduler = threading.Thread(target=schedule_loop, daemon=True)
    scheduler.start()
    
    # Resolve frontend index.html path (supports frozen PyInstaller build and dev mode)
    frontend_path = get_resource_path(os.path.join("frontend", "index.html"))
    
    window = webview.create_window(
        'Argus PII Guard', 
        url=frontend_path,
        js_api=api,
        width=1040, 
        height=720,
        min_size=(850, 600)
    )
    api.set_window(window)
    
    icon_path = get_resource_path(os.path.join("frontend", "assets", "argus-icon.ico"))
    if not os.path.exists(icon_path):
        icon_path = get_resource_path(os.path.join("frontend", "assets", "argus-icon.png"))
        
    webview.start(debug=False, icon=icon_path if os.path.exists(icon_path) else None)

if __name__ == '__main__':
    main()
