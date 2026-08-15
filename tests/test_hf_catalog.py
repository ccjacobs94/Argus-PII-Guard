"""
Unit tests for backend/hf_catalog.py - Dynamic Hugging Face GGUF catalog discovery.
"""

import json
import time
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.hf_catalog import (
    DEFAULT_CACHE_TTL_SECONDS,
    build_hf_model_entry,
    detect_vision_capability,
    estimate_ram_requirements,
    estimate_size_gb,
    fetch_hf_api_models,
    get_dynamic_model_catalog,
    load_cached_catalog,
    merge_with_curated_catalog,
    parse_model_quant,
    parse_param_size,
    query_huggingface_catalog,
    save_cached_catalog,
    select_best_gguf_file,
)


class TestHFCatalogParsing:
    def test_parse_model_quant(self):
        assert parse_model_quant("qwen2.5-7b-instruct-q4_k_m.gguf") == "Q4_K_M"
        assert parse_model_quant("gemma-3-1b-it-q8_0.gguf") == "Q8_0"
        assert parse_model_quant("moondream2-text-model-f16.gguf") == "F16"
        assert parse_model_quant("model-iq3_m.gguf") == "IQ3_M"
        assert parse_model_quant("unknown-model.gguf") == "Q4_K_M"

    def test_parse_param_size(self):
        assert parse_param_size("Qwen/Qwen2.5-1.5B-Instruct-GGUF") == 1.5
        assert parse_param_size("microsoft/Phi-4-mini-instruct-gguf 3.8b") == 3.8
        assert parse_param_size("mistralai/Mistral-Small-24B-Instruct-2501") == 24.0
        assert parse_param_size("unknown-model-repo") == 7.0

    def test_detect_vision_capability(self):
        assert detect_vision_capability("google/gemma-3-4b-it", ["image-text-to-text"]) is True
        assert detect_vision_capability("vikhyatk/moondream2", ["vision"]) is True
        assert detect_vision_capability("cjpais/llava-v1.6-mistral-7b-gguf", []) is True
        assert detect_vision_capability("Qwen/Qwen2-VL-7B-Instruct-GGUF", []) is True
        assert detect_vision_capability("Qwen/Qwen2.5-7B-Instruct-GGUF", ["text-generation"]) is False

    def test_estimate_size_gb(self):
        assert estimate_size_gb(7.0, "Q4_K_M") == 4.2
        assert estimate_size_gb(7.0, "Q8_0") == 8.0
        assert estimate_size_gb(2.0, "F16") == 4.1
        assert estimate_size_gb(14.0, "Q5_K_M") == 10.1
        assert estimate_size_gb(14.0, "Q3_K_M") == 6.7
        assert estimate_size_gb(14.0, "Q2_K") == 5.3

    def test_estimate_ram_requirements(self):
        min_ram, rec_ram = estimate_ram_requirements(4.2)
        assert min_ram >= 6
        assert rec_ram >= 8
        # Constrained sizes still respect floor
        min_ram_small, rec_ram_small = estimate_ram_requirements(0.5)
        assert min_ram_small >= 4
        assert rec_ram_small >= 6

    def test_select_best_gguf_file(self):
        siblings = [
            {"rfilename": "README.md"},
            {"rfilename": "model-q8_0.gguf"},
            {"rfilename": "model-q4_k_m.gguf"},
            {"rfilename": "model-q4_k_m-00001-of-00002.gguf"},
            {"rfilename": "model-f16.gguf"},
        ]
        best = select_best_gguf_file(siblings)
        assert best is not None
        assert best["rfilename"] == "model-q4_k_m.gguf"

        # No gguf files
        assert select_best_gguf_file([{"rfilename": "notes.txt"}]) is None

    def test_build_hf_model_entry(self):
        repo_data = {
            "id": "bartowski/Llama-3.2-3B-Instruct-GGUF",
            "downloads": 50000,
            "likes": 200,
            "tags": ["gguf", "llama-3", "text-generation"],
            "description": "Llama 3.2 3B Instruct GGUF",
            "siblings": [
                {"rfilename": "Llama-3.2-3B-Instruct-Q4_K_M.gguf", "size": 2 * 1024 ** 3}
            ],
        }
        entry = build_hf_model_entry(repo_data)
        assert entry is not None
        assert entry["name"] == "Llama-3.2-3B-Instruct"
        assert entry["filename"] == "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
        assert entry["params_b"] == 3.0
        assert entry["quant"] == "Q4_K_M"
        assert entry["size_gb"] == 2.0
        assert entry["source"] == "huggingface"
        assert entry["download_url"].startswith("https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/")

        # Empty repo ID returns None
        assert build_hf_model_entry({}) is None

        # Repo with no siblings constructs fallback
        no_siblings_entry = build_hf_model_entry({"id": "org/Secret-PII-Detector-7B"})
        assert no_siblings_entry is not None
        assert "secret-pii-detector-7b" in no_siblings_entry["filename"]


class TestHFCachingAndMerge:
    def test_save_and_load_cache(self, tmp_path):
        cache_file = str(tmp_path / "test_cache.json")
        models = [{"name": "TestModel", "filename": "test.gguf", "size_gb": 2.0}]

        assert load_cached_catalog(cache_path=cache_file) is None
        assert save_cached_catalog(models, cache_path=cache_file) is True

        loaded = load_cached_catalog(cache_path=cache_file, ttl_seconds=60)
        assert loaded is not None
        assert len(loaded) == 1
        assert loaded[0]["name"] == "TestModel"

    def test_load_cache_expired(self, tmp_path):
        cache_file = str(tmp_path / "expired_cache.json")
        payload = {"timestamp": time.time() - 500, "models": [{"name": "Old"}]}
        Path(cache_file).write_text(json.dumps(payload), encoding="utf-8")

        assert load_cached_catalog(cache_path=cache_file, ttl_seconds=100) is None
        # But with huge TTL, it loads stale
        assert load_cached_catalog(cache_path=cache_file, ttl_seconds=1000) is not None

    def test_load_cache_corrupt(self, tmp_path):
        cache_file = str(tmp_path / "corrupt.json")
        Path(cache_file).write_text("invalid json {", encoding="utf-8")
        assert load_cached_catalog(cache_path=cache_file) is None

    def test_merge_with_curated_catalog(self):
        curated = [
            {"name": "Qwen2.5-1.5B", "filename": "qwen2.5-1.5b.gguf", "size_gb": 1.6},
            {"name": "Phi-4 Mini", "filename": "phi-4-mini.gguf", "size_gb": 2.3},
        ]
        dynamic = [
            {"name": "Qwen Duplicate", "filename": "QWEN2.5-1.5B.GGUF", "size_gb": 1.6},
            {"name": "New HF Model", "filename": "new-hf-model.gguf", "size_gb": 4.0},
        ]

        merged = merge_with_curated_catalog(dynamic, curated)
        assert len(merged) == 3
        assert merged[0]["filename"] == "qwen2.5-1.5b.gguf"
        assert merged[0]["source"] == "curated"
        assert merged[2]["filename"] == "new-hf-model.gguf"


class TestHFNetworkAndFallback:
    @patch("urllib.request.urlopen")
    def test_fetch_hf_api_models_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps([
            {"id": "test/model-1", "siblings": [{"rfilename": "model1.gguf"}]}
        ]).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        res = fetch_hf_api_models({"filter": "gguf"})
        assert len(res) == 1
        assert res[0]["id"] == "test/model-1"

    @patch("urllib.request.urlopen")
    def test_fetch_hf_api_models_non_200(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 404
        mock_urlopen.return_value.__enter__.return_value = mock_response

        res = fetch_hf_api_models({"filter": "gguf"})
        assert res == []

    @patch("backend.hf_catalog.fetch_hf_api_models")
    def test_query_huggingface_catalog(self, mock_fetch):
        mock_fetch.side_effect = [
            [{"id": "org/repo-a", "siblings": [{"rfilename": "a-q4_k_m.gguf"}]}],
            [{"id": "org/repo-a"}, {"id": "org/repo-b", "siblings": [{"rfilename": "b-q4_k_m.gguf"}]}],
            Exception("Network error"),
        ]

        results = query_huggingface_catalog(queries=[{"q": 1}, {"q": 2}, {"q": 3}])
        assert len(results) == 2
        repo_ids = {r["repo_id"] for r in results}
        assert repo_ids == {"org/repo-a", "org/repo-b"}

    def test_get_dynamic_model_catalog_cache_hit(self, tmp_path):
        cache_file = str(tmp_path / "hit_cache.json")
        cached_models = [{"name": "Cached", "filename": "cached.gguf", "source": "huggingface"}]
        save_cached_catalog(cached_models, cache_path=cache_file)

        curated = [{"name": "Curated", "filename": "curated.gguf"}]
        res = get_dynamic_model_catalog(force_refresh=False, cache_path=cache_file, curated_catalog=curated)
        assert len(res) == 2
        filenames = [m["filename"] for m in res]
        assert "curated.gguf" in filenames
        assert "cached.gguf" in filenames

    @patch("backend.hf_catalog.query_huggingface_catalog")
    def test_get_dynamic_model_catalog_force_refresh(self, mock_query, tmp_path):
        cache_file = str(tmp_path / "fresh_cache.json")
        mock_query.return_value = [
            {"name": "Fresh Model", "filename": "fresh.gguf", "source": "huggingface"}
        ]
        curated = [{"name": "Curated", "filename": "curated.gguf"}]

        res = get_dynamic_model_catalog(force_refresh=True, cache_path=cache_file, curated_catalog=curated)
        assert len(res) == 2
        assert any(m["filename"] == "fresh.gguf" for m in res)
        # Check that it saved to cache
        loaded = load_cached_catalog(cache_path=cache_file)
        assert loaded is not None

    @patch("backend.hf_catalog.query_huggingface_catalog", side_effect=Exception("Connection timed out"))
    def test_get_dynamic_model_catalog_fallback_on_network_error(self, mock_query, tmp_path):
        cache_file = str(tmp_path / "fallback_cache.json")
        curated = [{"name": "Curated Model", "filename": "curated.gguf", "size_gb": 2.0}]

        # No cache + network failure -> fallback to curated
        res = get_dynamic_model_catalog(force_refresh=True, cache_path=cache_file, curated_catalog=curated)
        assert len(res) == 1
        assert res[0]["filename"] == "curated.gguf"
        assert res[0]["source"] == "curated"

    @patch("backend.hf_catalog.query_huggingface_catalog", side_effect=Exception("API down"))
    def test_get_dynamic_model_catalog_stale_cache_fallback(self, mock_query, tmp_path):
        cache_file = str(tmp_path / "stale_cache.json")
        # Save a stale cache with old timestamp
        payload = {"timestamp": 100.0, "models": [{"name": "Stale Model", "filename": "stale.gguf"}]}
        Path(cache_file).write_text(json.dumps(payload), encoding="utf-8")

        curated = [{"name": "Curated", "filename": "curated.gguf"}]
        res = get_dynamic_model_catalog(force_refresh=True, cache_path=cache_file, curated_catalog=curated)
        filenames = [m["filename"] for m in res]
        assert "curated.gguf" in filenames
        assert "stale.gguf" in filenames

    def test_get_dynamic_model_catalog_default_base_catalog(self, tmp_path):
        cache_file = str(tmp_path / "default_cache.json")
        cached = [{"name": "Default Test", "filename": "def.gguf"}]
        save_cached_catalog(cached, cache_path=cache_file)
        res = get_dynamic_model_catalog(force_refresh=False, cache_path=cache_file)
        assert len(res) >= 1

    def test_save_cached_catalog_error(self):
        # Invalid directory path triggers exception
        assert save_cached_catalog([], cache_path="/invalid/nonexistent/dir/cache.json") is False

    def test_select_best_gguf_unknown_quant(self):
        siblings = [{"rfilename": "model-customquant.gguf"}]
        best = select_best_gguf_file(siblings)
        assert best is not None
        assert best["rfilename"] == "model-customquant.gguf"

    @patch("urllib.request.urlopen")
    def test_fetch_hf_api_models_non_list(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({"error": "not found"}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        res = fetch_hf_api_models({"filter": "gguf"})
        assert res == []

    def test_estimate_size_gb_all_quants(self):
        assert estimate_size_gb(10.0, "bf16") == 20.5
        assert estimate_size_gb(10.0, "q3_k_m") == 4.8
        assert estimate_size_gb(10.0, "q2_k") == 3.8
        assert estimate_size_gb(10.0, "unknown") == 6.0

