"""
Model downloader engine for Argus PII Guard.

Provides non-blocking, chunked HTTP streaming model downloads with real-time
progress telemetry, cancellation, and clean temporary file management.
"""

import os
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional

_download_lock = threading.Lock()
_download_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()

_download_state: dict[str, Any] = {
    "status": "idle",  # "idle", "downloading", "completed", "cancelled", "error"
    "filename": "",
    "downloaded_bytes": 0,
    "total_bytes": 0,
    "percent": 0.0,
    "speed_mbps": 0.0,
    "error": None,
}


def _safe_unlink(path: Path) -> None:
    """Safely removes a file if it exists, suppressing any filesystem exceptions."""
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def get_download_status() -> dict[str, Any]:
    """Returns a snapshot copy of the current download status telemetry."""
    with _download_lock:
        return dict(_download_state)


def _reset_state(
    status: str = "idle",
    filename: str = "",
    total_bytes: int = 0,
    error: Optional[str] = None,
) -> None:
    """Reset the download state dictionary. Caller should hold _download_lock or run in thread init."""
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


def _download_worker(url: str, dest_folder: str, filename: str) -> None:
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

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ArgusPIIGuard/1.0",
            "Accept": "*/*",
        },
    )

    try:
        response = urllib.request.urlopen(request, timeout=15)
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

                elapsed = max(time.time() - start_time, 0.001)
                speed = (downloaded / (1024 * 1024)) / elapsed
                percent = round((downloaded / total_size * 100), 1) if total_size > 0 else 0.0

                with _download_lock:
                    _download_state["downloaded_bytes"] = downloaded
                    _download_state["percent"] = min(percent, 100.0)
                    _download_state["speed_mbps"] = round(speed, 2)

        if _stop_event.is_set():
            _safe_unlink(tmp_path)
            with _download_lock:
                _download_state["status"] = "cancelled"
                _download_state["error"] = None
            return

        # Download completed successfully — move temp file to target
        if tmp_path.exists():
            _safe_unlink(target_path)
            tmp_path.rename(target_path)

        with _download_lock:
            _download_state["status"] = "completed"
            _download_state["downloaded_bytes"] = total_size or downloaded
            _download_state["percent"] = 100.0
            _download_state["speed_mbps"] = 0.0
            _download_state["error"] = None

    except Exception as e:
        _safe_unlink(tmp_path)
        with _download_lock:
            _download_state["status"] = "error"
            _download_state["error"] = str(e)


def start_download(url: str, dest_folder: str, filename: str) -> tuple[bool, str]:
    """
    Spawns a background download worker thread if no download is currently active.
    Returns (success, message_or_error).
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
            daemon=True,
        )
        _download_thread.start()
        return True, "Download started."


def cancel_download() -> tuple[bool, str]:
    """Cancels the active model download if currently running."""
    global _stop_event
    with _download_lock:
        if _download_state["status"] != "downloading":
            return False, "No active download to cancel."
        _stop_event.set()
    return True, "Download cancellation requested."
