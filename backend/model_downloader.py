"""
Model downloader engine for Argus PII Guard.

Provides non-blocking, chunked HTTP streaming model downloads with real-time
progress telemetry, cancellation, and clean temporary file management.
"""

import os
import time
import threading
import urllib.request
from pathlib import Path


_download_lock = threading.Lock()
_download_thread = None
_stop_event = threading.Event()

_download_state = {
    "status": "idle",       # "idle", "downloading", "completed", "cancelled", "error"
    "filename": "",
    "downloaded_bytes": 0,
    "total_bytes": 0,
    "percent": 0.0,
    "speed_mbps": 0.0,
    "error": None,
}


def get_download_status():
    """Returns a snapshot copy of the current download status telemetry."""
    with _download_lock:
        return dict(_download_state)


def _reset_state(status="idle", filename="", total_bytes=0, error=None):
    """Reset state dictionary. Caller should hold _download_lock or run in thread init."""
    global _download_state
    _download_state = {
        "status": status,
        "filename": filename,
        "downloaded_bytes": 0,
        "total_bytes": total_bytes,
        "percent": 0.0,
        "speed_mbps": 0.0,
        "error": error,
    }


def _download_worker(url, dest_folder, filename):
    """Background worker thread executing the chunked HTTP download."""
    global _download_state
    
    dest_dir = Path(dest_folder)
    if not dest_dir.exists():
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            with _download_lock:
                _download_state["status"] = "error"
                _download_state["error"] = f"Failed to create directory: {str(e)}"
            return

    target_path = dest_dir / filename
    tmp_path = dest_dir / f"{filename}.tmp"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ArgusPIIGuard/1.0",
            "Accept": "*/*",
        }
    )

    try:
        # Open URL
        response = urllib.request.urlopen(req, timeout=15)
        total_size = int(response.headers.get("Content-Length", 0))

        with _download_lock:
            _download_state["status"] = "downloading"
            _download_state["filename"] = filename
            _download_state["total_bytes"] = total_size

        downloaded = 0
        start_time = time.time()
        chunk_size = 1024 * 1024  # 1 MB chunks

        with open(tmp_path, "wb") as f:
            while not _stop_event.is_set():
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                
                f.write(chunk)
                downloaded += len(chunk)

                elapsed = time.time() - start_time
                speed = (downloaded / (1024 * 1024)) / max(elapsed, 0.001)
                percent = round((downloaded / total_size * 100), 1) if total_size > 0 else 0.0

                with _download_lock:
                    _download_state["downloaded_bytes"] = downloaded
                    _download_state["percent"] = min(percent, 100.0)
                    _download_state["speed_mbps"] = round(speed, 2)

        if _stop_event.is_set():
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            with _download_lock:
                _download_state["status"] = "cancelled"
                _download_state["error"] = None
            return

        # Success - rename tmp to target
        if tmp_path.exists():
            if target_path.exists():
                target_path.unlink()
            tmp_path.rename(target_path)

        with _download_lock:
            _download_state["status"] = "completed"
            _download_state["downloaded_bytes"] = total_size or downloaded
            _download_state["percent"] = 100.0
            _download_state["speed_mbps"] = 0.0
            _download_state["error"] = None

    except Exception as e:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        with _download_lock:
            _download_state["status"] = "error"
            _download_state["error"] = str(e)


def start_download(url, dest_folder, filename):
    """
    Spawns background download thread if no download is currently active.
    Returns (success: bool, message_or_error: str).
    """
    global _download_thread, _stop_event

    if not url or not dest_folder or not filename:
        return False, "Missing download URL, folder, or filename."

    with _download_lock:
        if _download_state["status"] == "downloading":
            return False, "A model download is already in progress."

        _stop_event.clear()
        _reset_state(status="downloading", filename=filename)

        _download_thread = threading.Thread(
            target=_download_worker,
            args=(url, dest_folder, filename),
            daemon=True
        )
        _download_thread.start()
        return True, "Download started."


def cancel_download():
    """Cancels active download if running."""
    global _stop_event
    with _download_lock:
        if _download_state["status"] != "downloading":
            return False, "No active download to cancel."
        _stop_event.set()
    return True, "Download cancellation requested."
