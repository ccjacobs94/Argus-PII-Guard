import os
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import backend.model_downloader as downloader


class TestModelDownloader:
    def setup_method(self):
        downloader.cancel_download()
        downloader._reset_state()

    def test_get_download_status_initial(self):
        status = downloader.get_download_status()
        assert status["status"] == "idle"
        assert status["downloaded_bytes"] == 0
        assert status["percent"] == 0.0

    def test_start_download_invalid_args(self):
        success, msg = downloader.start_download("", "folder", "filename.gguf")
        assert success is False
        assert "Missing download URL" in msg

    def test_start_download_busy(self):
        with patch.object(downloader, "_download_state", {"status": "downloading"}):
            success, msg = downloader.start_download("http://example.com/model.gguf", "folder", "model.gguf")
            assert success is False
            assert "already in progress" in msg

    def test_cancel_download_when_idle(self):
        success, msg = downloader.cancel_download()
        assert success is False
        assert "No active download" in msg

    def test_download_worker_success(self, tmp_path):
        dest_folder = str(tmp_path)
        filename = "test_model.gguf"
        fake_data = b"GGUF_TEST_DATA_" * 100

        mock_response = MagicMock()
        mock_response.headers = {"Content-Length": str(len(fake_data))}
        # Simulate reading in chunks
        mock_response.read.side_effect = [fake_data, b""]

        with patch("urllib.request.urlopen", return_value=mock_response):
            success, msg = downloader.start_download("http://example.com/test_model.gguf", dest_folder, filename)
            assert success is True

            # Wait for thread to finish
            if downloader._download_thread:
                downloader._download_thread.join(timeout=2.0)

            status = downloader.get_download_status()
            assert status["status"] == "completed"
            assert status["percent"] == 100.0
            assert status["downloaded_bytes"] == len(fake_data)

            target = tmp_path / filename
            assert target.exists()
            assert target.read_bytes() == fake_data

    def test_download_worker_cancellation(self, tmp_path):
        dest_folder = str(tmp_path)
        filename = "cancel_model.gguf"
        chunk_data = b"CHUNK_" * 100

        def slow_read(chunk_size):
            time.sleep(0.05)
            return chunk_data

        mock_response = MagicMock()
        mock_response.headers = {"Content-Length": "100000"}
        mock_response.read.side_effect = slow_read

        with patch("urllib.request.urlopen", return_value=mock_response):
            downloader.start_download("http://example.com/cancel.gguf", dest_folder, filename)
            time.sleep(0.02)
            cancelled, msg = downloader.cancel_download()
            assert cancelled is True

            if downloader._download_thread:
                downloader._download_thread.join(timeout=2.0)

            status = downloader.get_download_status()
            assert status["status"] in ("cancelled", "downloading")
            # Tmp file should be cleaned up
            tmp_file = tmp_path / f"{filename}.tmp"
            assert not tmp_file.exists()

    def test_download_worker_error(self, tmp_path):
        dest_folder = str(tmp_path)
        filename = "error_model.gguf"

        with patch("urllib.request.urlopen", side_effect=Exception("HTTP 404 Not Found")):
            downloader.start_download("http://example.com/404.gguf", dest_folder, filename)
            if downloader._download_thread:
                downloader._download_thread.join(timeout=2.0)

            status = downloader.get_download_status()
            assert status["status"] == "error"
            assert "HTTP 404" in status["error"]
