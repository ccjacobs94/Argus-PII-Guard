import os
from pathlib import Path
from unittest.mock import MagicMock, patch
from PIL import Image
import pytest
from backend.main import Api, schedule_loop
from backend.state import load_cache, load_results, save_results, save_settings
import backend.scanner as scanner

@pytest.fixture
def api_instance():
    api = Api()
    mock_window = MagicMock()
    mock_window.create_file_dialog.return_value = ["C:/SelectedFolder"]
    api.set_window(mock_window)
    return api

def test_api_system_info(api_instance):
    info = api_instance.get_system_info()
    assert "ram_gb" in info
    assert info["ram_gb"] > 0
    assert "recommended_concurrency" in info

def test_api_system_info_exception(api_instance):
    with patch("backend.main.get_system_ram", side_effect=Exception("RAM error")):
        err_info = api_instance.get_system_info()
        assert "error" in err_info
        assert "RAM error" in err_info["error"]

def test_api_settings_crud(api_instance):
    settings = api_instance.get_settings()
    assert isinstance(settings, dict)

    settings["concurrency"] = "8"
    assert api_instance.save_settings(settings) is True
    updated = api_instance.get_settings()
    assert updated["concurrency"] == "8"

def test_api_results_crud(api_instance):
    initial = api_instance.get_results()
    assert initial == []

    new_results = [{"file": "leak.txt", "type": "Text", "reason": "SSN"}]
    assert api_instance.save_results(new_results) is True
    assert api_instance.get_results() == new_results

def test_api_select_folder(api_instance):
    folders = api_instance.select_folder()
    assert folders == ["C:/SelectedFolder"]

    # When window is None
    api_instance.set_window(None)
    assert api_instance.select_folder() == []

def test_api_check_ollama(api_instance):
    with patch("backend.main.ensure_ollama_running", return_value=(True, "Ollama running")):
        res = api_instance.check_ollama()
        assert res["success"] is True
        assert res["message"] == "Ollama running"

def test_api_start_and_stop_scan(api_instance, tmp_path):
    target_dir = tmp_path / "TargetDir"
    target_dir.mkdir()
    save_settings({"folders": [str(target_dir)]})
    with patch("backend.main.start_scan_thread", return_value=True) as mock_scan:
        res = api_instance.start_scan(rescan_all=True)
        assert res["success"] is True
        mock_scan.assert_called_once()
        # Verify callback invoked
        callback = mock_scan.call_args[0][1]
        callback([{"file": "cb_file.txt", "type": "Text"}])
        assert len(api_instance.get_results()) == 1

    # When folders empty
    save_settings({"folders": []})
    res_empty = api_instance.start_scan()
    assert res_empty["success"] is False
    assert res_empty["error"] == "no_directories"

    # When folders do not exist on disk
    save_settings({"folders": [str(tmp_path / "non_existent_folder")]})
    res_invalid = api_instance.start_scan()
    assert res_invalid["success"] is False
    assert res_invalid["error"] == "invalid_directories"

    # When scan thread fails to start
    save_settings({"folders": [str(target_dir)]})
    with patch("backend.main.start_scan_thread", return_value=False):
        res_busy = api_instance.start_scan()
        assert res_busy["success"] is False
        assert res_busy["error"] == "scan_in_progress"

    assert api_instance.stop_scan()["success"] is True


def test_api_mark_file_ok_and_cache(api_instance, tmp_path):
    test_file = tmp_path / "false_positive.txt"
    test_file.write_text("123-45-6789 mock data", encoding="utf-8")

    save_results([{"file": str(test_file), "type": "Text", "reason": "SSN"}])
    assert len(api_instance.get_results()) == 1

    # Mark as OK
    res = api_instance.mark_file_ok(str(test_file))
    assert res["success"] is True

    # Results should be cleared
    assert len(api_instance.get_results()) == 0

    # Cache should record cleared status with checksum and size
    cache = load_cache()
    assert str(test_file) in cache
    assert cache[str_file_key := str(test_file)]["result"]["compromised"] is False
    assert cache[str_file_key]["result"]["marked_ok"] is True
    assert "checksum" in cache[str_file_key]
    assert len(cache[str_file_key]["checksum"]) == 64
    assert "size" in cache[str_file_key]

def test_api_verify_file_ai(api_instance, tmp_path):
    f_comp = tmp_path / "comp.txt"
    f_comp.write_text("compromised secret")
    
    save_results([{"file": str(f_comp), "type": "Text", "reason": "Regex SSN", "needs_ai_verification": True}])
    scanner.scan_state.flagged_files = [{"file": str(f_comp), "type": "Text", "reason": "Regex SSN", "needs_ai_verification": True}]

    # Case 1: AI confirms compromised
    with patch("backend.scanner.verify_text_file_with_ai", return_value={"compromised": True, "reason": "AI Confirmed SSN"}):
        res = api_instance.verify_file(str(f_comp))
        assert res["success"] is True
        assert res["result"]["compromised"] is True
        updated_res = api_instance.get_results()
        assert updated_res[0]["verified_true"] is True
        assert updated_res[0]["compromised"] is True
        assert updated_res[0]["reason"] == "AI Confirmed SSN"

    # Case 2: AI clears file (False positive)
    with patch("backend.scanner.verify_text_file_with_ai", return_value={"compromised": False, "reason": "AI Cleared"}):
        res_clear = api_instance.verify_file(str(f_comp))
        assert res_clear["success"] is True
        assert len(api_instance.get_results()) == 0
        cache = load_cache()
        assert cache[str(f_comp)]["result"]["compromised"] is False
        assert "checksum" in cache[str(f_comp)]
        assert len(cache[str(f_comp)]["checksum"]) == 64
        assert "size" in cache[str(f_comp)]

    # Case 3: Verify file that doesn't exist in results or state
    with patch("backend.scanner.verify_text_file_with_ai", return_value={"compromised": True, "reason": "Random"}):
        res_other = api_instance.verify_file("C:/other.txt")
        assert res_other["success"] is True

def test_api_delete_files(api_instance, tmp_path):
    f1 = tmp_path / "del1.txt"
    f2 = tmp_path / "del2.txt"
    f1.write_text("data 1")
    f2.write_text("data 2")

    save_results([
        {"file": str(f1), "type": "Text", "reason": "SSN"},
        {"file": str(f2), "type": "Text", "reason": "Card"}
    ])
    scanner.scan_state.flagged_files = [
        {"file": str(f1), "type": "Text", "reason": "SSN"},
        {"file": str(f2), "type": "Text", "reason": "Card"}
    ]

    deleted = api_instance.delete_files([str(f1), "C:/non_existent_file.txt"])
    assert str(f1) in deleted
    assert not f1.exists()
    assert f2.exists()

    # Results list and state updated
    remaining = api_instance.get_results()
    assert len(remaining) == 1
    assert remaining[0]["file"] == str(f2)
    assert len(scanner.scan_state.flagged_files) == 1

def test_api_get_image_base64(api_instance, tmp_path):
    # Non-existent
    assert api_instance.get_image_base64("C:/non_existent_file.png") is None

    # Text / Document file
    text_file = tmp_path / "doc.txt"
    text_file.write_text("Sample confidential text", encoding="utf-8")
    content = api_instance.get_image_base64(str(text_file))
    assert "Sample confidential text" in content

    # Empty file message
    empty_file = tmp_path / "empty_doc.txt"
    empty_file.write_text("", encoding="utf-8")
    empty_msg = api_instance.get_image_base64(str(empty_file))
    assert "(No readable text" in empty_msg

    # Image file
    img_file = tmp_path / "sample.png"
    img = Image.new("RGB", (10, 10), color="red")
    img.save(str(img_file))
    img_data = api_instance.get_image_base64(str(img_file))
    assert img_data.startswith("data:image/jpeg;base64,") or img_data.startswith("data:image/png;base64,")

    # HEIC placeholder
    heic_file = tmp_path / "sample.heic"
    heic_file.write_text("fake heic")
    assert api_instance.get_image_base64(str(heic_file)) == "HEIC_FORMAT"

def test_api_get_file_preview_details(api_instance, tmp_path):
    # 1. Non-existent file
    res_none = api_instance.get_file_preview_details("C:/does_not_exist_file.txt")
    assert "error" in res_none

    # 2. Text file with PII highlights
    text_file = tmp_path / "confidential.txt"
    text_file.write_text("Line 1: Hello\nLine 2: SSN is 123-45-6789\nLine 3: Clean\n", encoding="utf-8")
    
    # Save a result record with reason and snippets
    api_instance.save_results([{
        "file": str(text_file),
        "type": "Text",
        "reason": "Contains SSN",
        "snippets": ["Hello"]
    }])
    
    res_text = api_instance.get_file_preview_details(str(text_file))
    assert res_text["content_type"] == "text"
    assert res_text["file_type"] == "Text"
    assert "checksum" in res_text
    assert len(res_text["checksum"]) == 64
    assert len(res_text["highlights"]) >= 2
    assert any(h["pattern_name"] == "SSN" for h in res_text["highlights"])
    assert any(h["source"] == "ai" for h in res_text["highlights"])

    # 3. Empty text file
    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("", encoding="utf-8")
    res_empty = api_instance.get_file_preview_details(str(empty_file))
    assert res_empty["content_type"] == "text"
    assert "(No readable text" in res_empty["content"]
    assert "checksum" in res_empty

    # 4. Image file with visual bounding box items
    img_file = tmp_path / "id_card.png"
    img = Image.new("RGB", (20, 20), color="blue")
    img.save(str(img_file))

    api_instance.save_results([{
        "file": str(img_file),
        "type": "Image",
        "reason": "ID Card visible",
        "items": [{
            "label": "Passport",
            "box_2d": [100, 100, 500, 500],
            "description": "Passport on desk"
        }]
    }])

    res_img = api_instance.get_file_preview_details(str(img_file))
    assert res_img["content_type"] == "image"
    assert res_img["file_type"] == "Image"
    assert "checksum" in res_img
    assert len(res_img["checksum"]) == 64
    assert res_img["data"].startswith("data:image/png;base64,")
    assert len(res_img["items"]) == 1
    assert res_img["items"][0]["label"] == "Passport"

    # 5. HEIC decoding in get_file_preview_details
    heic_img_path = tmp_path / "photo.heic"
    img.save(str(heic_img_path), "JPEG") # Saved in JPEG format inside .heic path
    res_heic = api_instance.get_file_preview_details(str(heic_img_path))
    assert res_heic["content_type"] == "image"
    assert res_heic["file_type"] == "HEIC"
    assert res_heic["data"].startswith("data:image/jpeg;base64,")

    # 6. Corrupt HEIC error handling
    corrupt_heic = tmp_path / "corrupt.heic"
    corrupt_heic.write_text("not an image binary")
    res_corrupt = api_instance.get_file_preview_details(str(corrupt_heic))
    assert "error" in res_corrupt

def test_api_scan_progress(api_instance):
    progress = api_instance.get_scan_progress()
    assert "is_scanning" in progress
    assert "progress" in progress
    assert "flagged_files" in progress
    assert "skipped_count" in progress["progress"]

def test_schedule_loop_triggered():
    save_settings({"schedule": {"enabled": True, "time": "14:30"}, "folders": ["C:/TestDir"]})
    scanner.scan_state.is_scanning = False
    
    with patch("time.strftime", return_value="14:30"):
        with patch("backend.main.start_scan_thread") as mock_scan:
            with patch("time.sleep", side_effect=StopIteration):
                try:
                    schedule_loop()
                except StopIteration:
                    pass
                mock_scan.assert_called_once()

def test_main_entrypoint():
    from backend.main import main
    with patch("backend.main.threading.Thread") as mock_thread, \
         patch("backend.main.webview.create_window") as mock_create_window, \
         patch("backend.main.webview.start") as mock_start:
        mock_t = MagicMock()
        mock_thread.return_value = mock_t
        main()
        mock_create_window.assert_called_once()
        mock_start.assert_called_once()
        mock_t.start.assert_called_once()


def test_get_resource_path_dev_mode():
    from backend.main import get_resource_path
    path = get_resource_path("frontend/index.html")
    assert os.path.isabs(path)
    assert path.endswith(os.path.join("frontend", "index.html"))

def test_get_resource_path_frozen_mode():
    from backend.main import get_resource_path
    with patch("sys._MEIPASS", "C:\\FakeBundlePath", create=True):
        path = get_resource_path("frontend/index.html")
        assert path == os.path.join("C:\\FakeBundlePath", "frontend/index.html")


# ============================================================================
# LOCAL MODEL MANAGEMENT API TESTS
# ============================================================================

def test_api_get_hardware_specs(api_instance):
    with patch("backend.main.get_full_system_specs", return_value={
        "ram_total_gb": 32.0, "ram_available_gb": 20.0,
        "cpu_name": "Test CPU", "cpu_cores": 8, "cpu_threads": 16,
        "gpu_name": "Test GPU", "gpu_vram_gb": 12.0, "os_platform": "win32"
    }):
        specs = api_instance.get_hardware_specs()
        assert specs["ram_total_gb"] == 32.0
        assert specs["cpu_name"] == "Test CPU"
        assert specs["gpu_vram_gb"] == 12.0

def test_api_get_hardware_specs_error(api_instance):
    with patch("backend.main.get_full_system_specs", side_effect=Exception("hw error")):
        result = api_instance.get_hardware_specs()
        assert "error" in result

def test_api_get_recommended_models(api_instance):
    mock_specs = {
        "ram_total_gb": 16, "ram_available_gb": 12,
        "cpu_name": "Test", "cpu_cores": 8, "cpu_threads": 16,
        "gpu_name": None, "gpu_vram_gb": None, "os_platform": "win32"
    }
    with patch("backend.main.get_full_system_specs", return_value=mock_specs):
        with patch("backend.main.get_recommended_models", return_value=[
            {"name": "Model A", "fit_score": 90, "fit_tier": "Excellent"}
        ]) as mock_rec:
            result = api_instance.get_recommended_models(force_refresh=True)
            mock_rec.assert_called_once_with(mock_specs, force_refresh=True)
            assert "specs" in result
            assert "models" in result
            assert len(result["models"]) == 1
            assert result["models"][0]["fit_score"] == 90

def test_api_get_recommended_models_error(api_instance):
    with patch("backend.main.get_full_system_specs", side_effect=Exception("fail")):
        result = api_instance.get_recommended_models()
        assert "error" in result

def test_api_scan_models_folder(api_instance, tmp_path):
    (tmp_path / "model.gguf").write_bytes(b"\x00" * 512)
    result = api_instance.scan_models_folder(str(tmp_path))
    assert "models" in result
    assert len(result["models"]) == 1
    assert result["models"][0]["filename"] == "model.gguf"

def test_api_scan_models_folder_no_folder(api_instance):
    result = api_instance.scan_models_folder()
    assert "error" in result

def test_api_scan_models_folder_from_settings(api_instance, tmp_path):
    (tmp_path / "test.gguf").write_bytes(b"\x00" * 256)
    save_settings({"folders": [], "models_folder": str(tmp_path)})
    result = api_instance.scan_models_folder()
    assert "models" in result
    assert len(result["models"]) == 1

def test_api_select_models_folder(api_instance, tmp_path):
    api_instance._window.create_file_dialog.return_value = [str(tmp_path)]
    folder = api_instance.select_models_folder()
    assert folder == str(tmp_path)

def test_api_select_models_folder_cancelled(api_instance):
    api_instance._window.create_file_dialog.return_value = None
    folder = api_instance.select_models_folder()
    assert folder is None

def test_api_select_models_folder_no_window():
    api = Api()
    folder = api.select_models_folder()
    assert folder is None

def test_api_load_local_model_not_available(api_instance, tmp_path):
    model_file = tmp_path / "test.gguf"
    model_file.write_bytes(b"\x00" * 100)
    with patch("backend.main.local_llm") as mock_llm:
        mock_llm.is_available.return_value = False
        result = api_instance.load_local_model(str(model_file))
        assert result["success"] is False
        assert "not installed" in result["error"]

def test_api_load_local_model_success(api_instance, tmp_path):
    model_file = tmp_path / "test.gguf"
    model_file.write_bytes(b"\x00" * 100)
    with patch("backend.main.local_llm") as mock_llm:
        mock_llm.is_available.return_value = True
        mock_llm.get_loaded_model_info.return_value = {"filename": "test.gguf", "status": "loaded"}
        result = api_instance.load_local_model(str(model_file))
        assert result["success"] is True
        assert result["info"]["filename"] == "test.gguf"

def test_api_load_local_model_error(api_instance, tmp_path):
    with patch("backend.main.local_llm") as mock_llm:
        mock_llm.is_available.return_value = True
        mock_llm.load_model.side_effect = Exception("load failed")
        result = api_instance.load_local_model("/fake/model.gguf")
        assert result["success"] is False
        assert "load failed" in result["error"]

def test_api_unload_local_model(api_instance):
    with patch("backend.main.local_llm") as mock_llm:
        result = api_instance.unload_local_model()
        assert result["success"] is True
        mock_llm.unload_model.assert_called_once()

def test_api_unload_local_model_error(api_instance):
    with patch("backend.main.local_llm") as mock_llm:
        mock_llm.unload_model.side_effect = Exception("unload error")
        result = api_instance.unload_local_model()
        assert result["success"] is False

def test_api_get_loaded_model_info_none(api_instance):
    with patch("backend.main.local_llm") as mock_llm:
        mock_llm.get_loaded_model_info.return_value = None
        result = api_instance.get_loaded_model_info()
        assert result is None

def test_api_get_loaded_model_info_loaded(api_instance):
    with patch("backend.main.local_llm") as mock_llm:
        mock_llm.get_loaded_model_info.return_value = {"filename": "test.gguf", "status": "loaded"}
        result = api_instance.get_loaded_model_info()
        assert result["filename"] == "test.gguf"

def test_settings_include_new_model_defaults(api_instance):
    settings = api_instance.get_settings()
    assert "model_provider" in settings
    assert settings["model_provider"] == "ollama"
    assert "models_folder" in settings
    assert "vision_model_name" in settings
    assert "text_model_name" in settings
    assert "local_vision_model" in settings
    assert "local_text_model" in settings

def test_api_download_recommended_model_no_folder(api_instance):
    with patch("backend.main.load_settings", return_value={"models_folder": ""}):
        result = api_instance.download_recommended_model("test.gguf", "http://example.com/test.gguf")
        assert result["success"] is False
        assert result["prompt_folder"] is True

def test_api_download_recommended_model_success(api_instance, tmp_path):
    with patch("backend.main.load_settings", return_value={"models_folder": str(tmp_path)}):
        with patch("backend.main.model_downloader.start_download", return_value=(True, "Download started.")):
            result = api_instance.download_recommended_model("test.gguf", "http://example.com/test.gguf")
            assert result["success"] is True
            assert result["filename"] == "test.gguf"

def test_api_download_recommended_model_error(api_instance):
    with patch("backend.main.load_settings", side_effect=Exception("Settings load error")):
        result = api_instance.download_recommended_model("test.gguf", "http://example.com/test.gguf")
        assert result["success"] is False
        assert "Settings load error" in result["error"]

def test_api_cancel_model_download(api_instance):
    with patch("backend.main.model_downloader.cancel_download", return_value=(True, "Cancelled.")):
        result = api_instance.cancel_model_download()
        assert result["success"] is True

def test_api_cancel_model_download_error(api_instance):
    with patch("backend.main.model_downloader.cancel_download", side_effect=Exception("Cancel error")):
        result = api_instance.cancel_model_download()
        assert result["success"] is False

def test_api_get_model_download_status(api_instance):
    mock_status = {"status": "downloading", "percent": 45.0}
    with patch("backend.main.model_downloader.get_download_status", return_value=mock_status):
        status = api_instance.get_model_download_status()
        assert status["status"] == "downloading"
        assert status["percent"] == 45.0


def test_api_remediation_methods_error_handling(api_instance):
    with patch("backend.main.remediation.redact_file_entity", side_effect=Exception("redact err")):
        res = api_instance.redact_entity("file.txt", 1, 0, 5, "secret")
        assert res["success"] is False
        assert "redact err" in res["error"]

    with patch("backend.main.remediation.batch_redact_file", side_effect=Exception("batch redact err")):
        res = api_instance.batch_redact("file.txt")
        assert res["success"] is False
        assert "batch redact err" in res["error"]

    with patch("backend.main.remediation.trash_or_delete_file", side_effect=Exception("delete err")):
        res = api_instance.delete_file_item("file.txt")
        assert res["success"] is False
        assert "delete err" in res["error"]

    with patch("backend.main.remediation.mark_as_safe_exception", side_effect=Exception("safe err")):
        res = api_instance.mark_as_safe("file.txt", "match")
        assert res["success"] is False
        assert "safe err" in res["error"]

    with patch("backend.main.remediation.get_allowed_exceptions", side_effect=Exception("list err")):
        res = api_instance.get_allowed_exceptions()
        assert "error" in res

    with patch("backend.main.remediation.remove_allowed_exception", side_effect=Exception("remove err")):
        res = api_instance.remove_allowed_exception("id_123")
        assert res["success"] is False

    with patch("backend.main.remediation.fix_file_permissions", side_effect=Exception("perm err")):
        res = api_instance.fix_file_permissions("file.txt")
        assert res["success"] is False

    with patch("backend.main.remediation.list_backups", side_effect=Exception("backup err")):
        res = api_instance.get_backups_list()
        assert "error" in res

    with patch("backend.main.remediation.restore_backup", side_effect=Exception("restore err")):
        res = api_instance.restore_backup_file("id_123")
        assert res["success"] is False

    with patch("backend.main.remediation.prune_expired_backups", side_effect=Exception("prune err")):
        res = api_instance.prune_backups()
        assert res["success"] is False




