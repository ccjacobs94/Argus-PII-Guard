import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock
from backend.local_llm import (
    scan_models_folder, load_model, unload_model,
    get_loaded_model_info, chat_completion, is_available,
    _loaded_model, _loaded_model_info, _loaded_model_path
)
import backend.local_llm as local_llm_module


class TestIsAvailable:
    def test_available_when_installed(self):
        # Since llama_cpp may or may not be installed, just ensure
        # the function returns a bool without error
        result = is_available()
        assert isinstance(result, bool)

    @patch.dict("sys.modules", {"llama_cpp": None})
    def test_not_available_when_missing(self):
        # Force import failure
        with patch("builtins.__import__", side_effect=ImportError("no module")):
            # Re-check; the function catches ImportError
            result = is_available()
            assert result is False


class TestScanModelsFolder:
    def test_scan_empty_folder(self, tmp_path):
        models = scan_models_folder(str(tmp_path))
        assert models == []

    def test_scan_nonexistent_folder(self):
        models = scan_models_folder("/nonexistent/folder/path/abc")
        assert models == []

    def test_scan_folder_with_gguf_files(self, tmp_path):
        # Create dummy .gguf files
        (tmp_path / "model-a.gguf").write_bytes(b"\x00" * 1024)
        (tmp_path / "model-b.gguf").write_bytes(b"\x00" * 2048)
        (tmp_path / "readme.txt").write_text("not a model")
        (tmp_path / "model.bin").write_bytes(b"\x00" * 512)

        models = scan_models_folder(str(tmp_path))
        assert len(models) == 2
        filenames = [m["filename"] for m in models]
        assert "model-a.gguf" in filenames
        assert "model-b.gguf" in filenames
        # Should not include non-gguf files
        assert "readme.txt" not in filenames
        assert "model.bin" not in filenames

    def test_scan_returns_metadata(self, tmp_path):
        data = b"\x00" * (1024 * 1024 * 100)  # ~100MB simulated
        model_file = tmp_path / "test-model.gguf"
        model_file.write_bytes(data)

        models = scan_models_folder(str(tmp_path))
        assert len(models) == 1
        m = models[0]
        assert m["filename"] == "test-model.gguf"
        assert m["path"] == str(model_file)
        assert m["size_bytes"] == len(data)
        assert m["size_gb"] == round(len(data) / (1024 ** 3), 2)

    def test_scan_ignores_directories(self, tmp_path):
        subdir = tmp_path / "submodel.gguf"
        subdir.mkdir()
        models = scan_models_folder(str(tmp_path))
        assert len(models) == 0

    def test_scan_case_insensitive_extension(self, tmp_path):
        (tmp_path / "model.GGUF").write_bytes(b"\x00" * 512)
        models = scan_models_folder(str(tmp_path))
        assert len(models) == 1


class TestLoadUnloadModel:
    def setup_method(self):
        """Reset module state before each test."""
        local_llm_module._loaded_model = None
        local_llm_module._loaded_model_path = None
        local_llm_module._loaded_model_info = None

    def test_load_raises_without_llama_cpp(self, tmp_path):
        model_file = tmp_path / "test.gguf"
        model_file.write_bytes(b"\x00" * 100)

        with patch("backend.local_llm.is_available", return_value=False):
            with pytest.raises(RuntimeError, match="not installed"):
                load_model(str(model_file))

    def test_load_raises_file_not_found(self):
        with patch("backend.local_llm.is_available", return_value=True):
            with pytest.raises(FileNotFoundError):
                load_model("/nonexistent/model.gguf")

    def test_load_and_unload_model(self, tmp_path):
        model_file = tmp_path / "test.gguf"
        model_file.write_bytes(b"\x00" * 100)

        mock_llama = MagicMock()
        mock_llama_class = MagicMock(return_value=mock_llama)

        with patch("backend.local_llm.is_available", return_value=True):
            with patch.dict("sys.modules", {"llama_cpp": MagicMock(Llama=mock_llama_class)}):
                with patch("backend.local_llm.llama_cpp", create=True) as mock_mod:
                    mock_mod.Llama = mock_llama_class
                    # Need to patch the import inside load_model
                    import importlib
                    with patch("builtins.__import__", side_effect=lambda name, *args, **kwargs: (
                        MagicMock(Llama=mock_llama_class) if name == "llama_cpp" 
                        else importlib.__import__(name, *args, **kwargs)
                    )):
                        result = load_model(str(model_file))
                        assert result is True

                        info = get_loaded_model_info()
                        assert info is not None
                        assert info["filename"] == "test.gguf"
                        assert info["status"] == "loaded"

                        unload_model()
                        assert get_loaded_model_info() is None

    def test_unload_when_nothing_loaded(self):
        # Should not raise
        result = unload_model()
        assert result is True
        assert get_loaded_model_info() is None


class TestChatCompletion:
    def setup_method(self):
        local_llm_module._loaded_model = None
        local_llm_module._loaded_model_path = None
        local_llm_module._loaded_model_info = None

    def test_raises_when_no_model_loaded(self):
        with pytest.raises(RuntimeError, match="No GGUF model"):
            chat_completion([{"role": "user", "content": "test"}])

    def test_chat_completion_returns_ollama_format(self):
        mock_model = MagicMock()
        mock_model.create_chat_completion.return_value = {
            "choices": [
                {"message": {"role": "assistant", "content": '{"compromised": false}'}}
            ]
        }

        local_llm_module._loaded_model = mock_model
        local_llm_module._loaded_model_info = {"status": "loaded", "filename": "test.gguf"}

        result = chat_completion([{"role": "user", "content": "test prompt"}])

        assert "message" in result
        assert result["message"]["role"] == "assistant"
        assert result["message"]["content"] == '{"compromised": false}'

        mock_model.create_chat_completion.assert_called_once()
        call_args = mock_model.create_chat_completion.call_args
        assert call_args[1]["temperature"] == 0.0

        # Cleanup
        local_llm_module._loaded_model = None
        local_llm_module._loaded_model_info = None

    def test_chat_completion_empty_response(self):
        mock_model = MagicMock()
        mock_model.create_chat_completion.return_value = {"choices": []}

        local_llm_module._loaded_model = mock_model
        local_llm_module._loaded_model_info = {"status": "loaded", "filename": "test.gguf"}

        result = chat_completion([{"role": "user", "content": "test"}])
        assert result["message"]["content"] == ""

        local_llm_module._loaded_model = None
        local_llm_module._loaded_model_info = None


class TestGetLoadedModelInfo:
    def setup_method(self):
        local_llm_module._loaded_model = None
        local_llm_module._loaded_model_path = None
        local_llm_module._loaded_model_info = None

    def test_returns_none_when_no_model(self):
        assert get_loaded_model_info() is None

    def test_returns_copy_not_reference(self):
        local_llm_module._loaded_model_info = {"status": "loaded", "filename": "test.gguf"}
        info = get_loaded_model_info()
        assert info is not local_llm_module._loaded_model_info
        assert info == {"status": "loaded", "filename": "test.gguf"}

        local_llm_module._loaded_model_info = None
