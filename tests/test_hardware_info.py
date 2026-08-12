import pytest
from unittest.mock import patch, MagicMock, mock_open
from backend.hardware_info import (
    get_cpu_info, get_gpu_info, get_ram_info,
    get_full_system_specs, compute_fit_score,
    get_recommended_models, MODEL_CATALOG
)


class TestModelCatalog:
    def test_catalog_not_empty(self):
        assert len(MODEL_CATALOG) > 0

    def test_catalog_required_keys(self):
        required = {"name", "filename", "params_b", "quant", "size_gb",
                     "min_ram_gb", "rec_ram_gb", "vision", "description", "url", "download_url"}
        for model in MODEL_CATALOG:
            missing = required - set(model.keys())
            assert not missing, f"Model '{model.get('name')}' missing keys: {missing}"

    def test_catalog_values_valid(self):
        for model in MODEL_CATALOG:
            assert model["params_b"] > 0
            assert model["size_gb"] > 0
            assert model["min_ram_gb"] > 0
            assert model["rec_ram_gb"] >= model["min_ram_gb"]
            assert isinstance(model["vision"], bool)
            assert model["url"].startswith("https://")
            assert model["download_url"].startswith("https://")

    def test_catalog_has_vision_models(self):
        vision_models = [m for m in MODEL_CATALOG if m["vision"]]
        assert len(vision_models) >= 2, "Should have at least 2 vision-capable models"

    def test_catalog_has_small_models(self):
        small = [m for m in MODEL_CATALOG if m["min_ram_gb"] <= 6]
        assert len(small) >= 2, "Should have models for ≤6GB RAM"


class TestCPUInfo:
    def test_returns_expected_keys(self):
        info = get_cpu_info()
        assert "cpu_name" in info
        assert "cpu_cores" in info
        assert "cpu_threads" in info
        assert info["cpu_threads"] >= 1
        assert info["cpu_cores"] >= 1

    @patch("sys.platform", "darwin")
    @patch("subprocess.check_output", side_effect=Exception("cmd failed"))
    def test_fallback_on_error(self, mock_sub):
        info = get_cpu_info()
        assert info["cpu_threads"] >= 1
        assert info["cpu_cores"] >= 1

    @patch("sys.platform", "linux")
    def test_cpu_info_linux(self):
        fake_cpuinfo = (
            "model name\t: Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz\n"
            "physical id\t: 0\n"
            "core id\t\t: 0\n"
            "physical id\t: 0\n"
            "core id\t\t: 1\n"
        )
        with patch("builtins.open", mock_open(read_data=fake_cpuinfo)):
            info = get_cpu_info()
            assert "Intel" in info["cpu_name"]
            assert info["cpu_cores"] == 2

    @patch("sys.platform", "darwin")
    def test_cpu_info_darwin(self):
        def fake_check_output(cmd, **kwargs):
            if "machdep.cpu.brand_string" in cmd:
                return "Apple M2 Max\n"
            if "hw.physicalcpu" in cmd:
                return "12\n"
            return ""

        with patch("subprocess.check_output", side_effect=fake_check_output):
            info = get_cpu_info()
            assert info["cpu_name"] == "Apple M2 Max"
            assert info["cpu_cores"] == 12

    @patch("sys.platform", "win32")
    def test_cpu_info_win32(self):
        def fake_check_output(cmd, **kwargs):
            if "NumberOfCores" in cmd:
                return "NumberOfCores\n8\n"
            return "Name\nAMD Ryzen 7 5800X\n"

        with patch("subprocess.check_output", side_effect=fake_check_output):
            info = get_cpu_info()
            assert "Ryzen" in info["cpu_name"]
            assert info["cpu_cores"] == 8


class TestGPUInfo:
    def test_returns_expected_keys(self):
        info = get_gpu_info()
        assert "gpu_name" in info
        assert "gpu_vram_gb" in info

    @patch("subprocess.check_output", side_effect=FileNotFoundError("nvidia-smi not found"))
    def test_no_gpu_returns_none(self, mock_sub):
        info = get_gpu_info()
        assert info["gpu_name"] is None
        assert info["gpu_vram_gb"] is None

    @patch("subprocess.check_output", return_value="NVIDIA GeForce RTX 4090, 24564\n")
    def test_nvidia_detected(self, mock_sub):
        info = get_gpu_info()
        assert info["gpu_name"] == "NVIDIA GeForce RTX 4090"
        assert info["gpu_vram_gb"] == round(24564 / 1024, 2)


class TestRAMInfo:
    @patch("backend.scanner.get_system_ram")
    def test_returns_expected_keys(self, mock_ram):
        mock_ram.return_value = 16 * (1024 ** 3)
        info = get_ram_info()
        assert "ram_total_gb" in info
        assert "ram_available_gb" in info
        assert info["ram_total_gb"] > 0
        assert info["ram_available_gb"] > 0

    @patch("sys.platform", "linux")
    @patch("backend.scanner.get_system_ram", return_value=16 * 1024**3)
    def test_ram_info_linux(self, mock_ram):
        fake_meminfo = (
            "MemTotal:       16384000 kB\n"
            "MemAvailable:    8192000 kB\n"
        )
        with patch("builtins.open", mock_open(read_data=fake_meminfo)):
            info = get_ram_info()
            assert info["ram_total_gb"] == 16.0
            assert info["ram_available_gb"] > 0

    @patch("sys.platform", "darwin")
    @patch("backend.scanner.get_system_ram", return_value=16 * 1024**3)
    def test_ram_info_darwin(self, mock_ram):
        fake_vm_stat = (
            "Mach Virtual Memory Statistics: (page size of 4096 bytes)\n"
            "Pages free:                              1000000.\n"
            "Pages inactive:                           500000.\n"
        )
        with patch("subprocess.check_output", return_value=fake_vm_stat):
            info = get_ram_info()
            assert info["ram_total_gb"] == 16.0
            assert info["ram_available_gb"] > 0


class TestFullSystemSpecs:
    @patch("backend.hardware_info.get_ram_info", return_value={"ram_total_gb": 32.0, "ram_available_gb": 20.0})
    @patch("backend.hardware_info.get_cpu_info", return_value={"cpu_name": "Test CPU", "cpu_cores": 8, "cpu_threads": 16})
    @patch("backend.hardware_info.get_gpu_info", return_value={"gpu_name": "Test GPU", "gpu_vram_gb": 12.0})
    def test_full_specs(self, mock_gpu, mock_cpu, mock_ram):
        specs = get_full_system_specs()
        assert specs["ram_total_gb"] == 32.0
        assert specs["ram_available_gb"] == 20.0
        assert specs["cpu_name"] == "Test CPU"
        assert specs["cpu_cores"] == 8
        assert specs["cpu_threads"] == 16
        assert specs["gpu_name"] == "Test GPU"
        assert specs["gpu_vram_gb"] == 12.0
        assert "os_platform" in specs


class TestComputeFitScore:
    def test_too_large_model(self):
        model = {"size_gb": 14, "min_ram_gb": 24, "rec_ram_gb": 32}
        specs = {"ram_total_gb": 8, "gpu_vram_gb": None}
        score, tier = compute_fit_score(model, specs)
        assert score == 0
        assert tier == "Too Large"

    def test_excellent_fit(self):
        model = {"size_gb": 1.1, "min_ram_gb": 4, "rec_ram_gb": 6}
        specs = {"ram_total_gb": 32, "gpu_vram_gb": None}
        score, tier = compute_fit_score(model, specs)
        assert score >= 80
        assert tier == "Excellent"

    def test_good_fit(self):
        model = {"size_gb": 4.1, "min_ram_gb": 8, "rec_ram_gb": 12}
        specs = {"ram_total_gb": 10, "gpu_vram_gb": None}
        score, tier = compute_fit_score(model, specs)
        assert 40 <= score < 80
        assert tier in ("Good", "Tight")

    def test_tight_fit(self):
        model = {"size_gb": 4.1, "min_ram_gb": 8, "rec_ram_gb": 12}
        specs = {"ram_total_gb": 8.5, "gpu_vram_gb": None}
        score, tier = compute_fit_score(model, specs)
        assert score > 0
        assert tier in ("Tight", "Good")

    def test_gpu_bonus(self):
        model = {"size_gb": 2.5, "min_ram_gb": 6, "rec_ram_gb": 10}
        specs_no_gpu = {"ram_total_gb": 12, "gpu_vram_gb": None}
        specs_gpu = {"ram_total_gb": 12, "gpu_vram_gb": 8.0}
        score_no, _ = compute_fit_score(model, specs_no_gpu)
        score_gpu, _ = compute_fit_score(model, specs_gpu)
        assert score_gpu >= score_no

    def test_score_capped_at_100(self):
        model = {"size_gb": 1.0, "min_ram_gb": 4, "rec_ram_gb": 6}
        specs = {"ram_total_gb": 128, "gpu_vram_gb": 48.0}
        score, tier = compute_fit_score(model, specs)
        assert score <= 100
        assert tier == "Excellent"

    def test_insufficient_headroom_too_large(self):
        model = {"size_gb": 7.0, "min_ram_gb": 6, "rec_ram_gb": 8}
        # 7.0 * 1.2 = 8.4GB required, total_ram is 8.0 => headroom <= 0
        specs = {"ram_total_gb": 8.0, "gpu_vram_gb": None}
        score, tier = compute_fit_score(model, specs)
        assert score == 0
        assert tier == "Too Large"


class TestGetRecommendedModels:
    @patch("backend.hardware_info.get_full_system_specs", return_value={
        "ram_total_gb": 16, "ram_available_gb": 12,
        "cpu_name": "Test", "cpu_cores": 8, "cpu_threads": 16,
        "gpu_name": None, "gpu_vram_gb": None, "os_platform": "win32"
    })
    def test_returns_annotated_models(self, mock_specs):
        results = get_recommended_models()
        assert len(results) == len(MODEL_CATALOG)
        for m in results:
            assert "fit_score" in m
            assert "fit_tier" in m
            assert m["fit_tier"] in ("Excellent", "Good", "Tight", "Too Large")

    @patch("backend.hardware_info.get_full_system_specs", return_value={
        "ram_total_gb": 16, "ram_available_gb": 12,
        "cpu_name": "Test", "cpu_cores": 8, "cpu_threads": 16,
        "gpu_name": None, "gpu_vram_gb": None, "os_platform": "win32"
    })
    def test_sorted_by_fit_score_desc(self, mock_specs):
        results = get_recommended_models()
        scores = [m["fit_score"] for m in results]
        assert scores == sorted(scores, reverse=True)

    def test_with_explicit_specs(self):
        specs = {
            "ram_total_gb": 4, "ram_available_gb": 3,
            "gpu_vram_gb": None
        }
        results = get_recommended_models(specs)
        too_large = [m for m in results if m["fit_tier"] == "Too Large"]
        assert len(too_large) > 0

    def test_high_ram_everything_fits(self):
        specs = {
            "ram_total_gb": 128, "ram_available_gb": 100,
            "gpu_vram_gb": 48.0
        }
        results = get_recommended_models(specs)
        too_large = [m for m in results if m["fit_tier"] == "Too Large"]
        assert len(too_large) == 0
