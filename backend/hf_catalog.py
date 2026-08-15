"""
Dynamic Hugging Face GGUF model catalog and discovery engine for Argus PII Guard.

Queries the Hugging Face Hub API for compatible PII and lightweight local models,
extracts GGUF file metadata, quantizations, and size metrics, computes RAM requirements,
and provides disk caching with seamless offline fallback to the curated model catalog.
"""

import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("argus.hf_catalog")

HF_MODELS_API = "https://huggingface.co/api/models"
HF_CACHE_FILE = "hf_models_cache.json"
DEFAULT_CACHE_TTL_SECONDS = 86400  # 24 hours

# Targeted search tags and queries for PII detection, redaction, and compact LLM/VLM inference
DEFAULT_HF_QUERIES = [
    {"filter": "gguf", "search": "pii", "limit": 10},
    {"filter": "gguf", "search": "redact", "limit": 10},
    {"filter": "gguf", "sort": "downloads", "direction": "-1", "limit": 20},
]

# Preferred quantization formats in order of recommendation
PREFERRED_QUANTS = ["q4_k_m", "q5_k_m", "q8_0", "q4_0", "q4_k_s", "f16"]

# Regex patterns for quant extraction and param sizes
QUANT_PATTERN = re.compile(
    r"\b(q[2-8]_[kK]_[sSmMlLiI]|q[2-8]_[0-9]|q[2-8]_[kK]|f16|f32|bf16|iq[1-4]_[a-zA-Z0-9_]+)\b",
    re.IGNORECASE,
)
PARAM_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*[bB]\b")


def parse_model_quant(filename: str) -> str:
    """Extracts quantization identifier from filename (e.g., 'Q4_K_M', 'Q8_0')."""
    match = QUANT_PATTERN.search(filename)
    if match:
        return match.group(1).upper()
    return "Q4_K_M"


def parse_param_size(name_or_repo: str) -> float:
    """Extracts parameter count in billions (e.g. 7.0 for 7B, 1.5 for 1.5B)."""
    match = PARAM_PATTERN.search(name_or_repo)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return 7.0


def detect_vision_capability(repo_id: str, tags: list[str]) -> bool:
    """Detects if a model supports vision/multimodal inference based on repo ID and tags."""
    vision_keywords = {"vision", "multimodal", "image-text-to-text", "llava", "moondream", "vl", "ocr"}
    tags_lower = {t.lower() for t in tags}
    if any(k in tags_lower for k in vision_keywords):
        return True

    repo_lower = repo_id.lower()
    return any(k in repo_lower for k in ["llava", "moondream", "-vl", "vision", "gemma-3-4b", "gemma-3-12b"])


def estimate_size_gb(params_b: float, quant: str) -> float:
    """Estimates GGUF file size in GB from parameter count and quantization level."""
    quant_lower = quant.lower()
    if "q8" in quant_lower:
        multiplier = 1.15
    elif "f16" in quant_lower or "bf16" in quant_lower:
        multiplier = 2.05
    elif "q5" in quant_lower:
        multiplier = 0.72
    elif "q3" in quant_lower:
        multiplier = 0.48
    elif "q2" in quant_lower:
        multiplier = 0.38
    else:  # Default to ~Q4
        multiplier = 0.60

    return round(params_b * multiplier, 1)


def estimate_ram_requirements(size_gb: float) -> tuple[int, int]:
    """
    Estimates minimum and recommended system RAM in GB for a given GGUF model size.
    Returns (min_ram_gb, rec_ram_gb).
    """
    min_ram = max(4, round(size_gb + 2.0))
    rec_ram = max(6, round(size_gb * 1.35 + 3.5))
    return min_ram, rec_ram


def select_best_gguf_file(siblings: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """
    Picks the single most appropriate, balanced .gguf file from a repository's file list.
    Excludes split multi-part files (*-00001-of-*.gguf).
    """
    gguf_files = []
    for f in siblings:
        rfilename = f.get("rfilename", "")
        if not rfilename.lower().endswith(".gguf"):
            continue
        # Skip multi-part split shards
        if re.search(r"-\d{5}-of-\d{5}\.gguf$", rfilename, re.IGNORECASE):
            continue
        gguf_files.append(f)

    if not gguf_files:
        return None

    # Score by quant preference
    def quant_priority(item: dict[str, Any]) -> int:
        fname = item.get("rfilename", "").lower()
        for idx, q in enumerate(PREFERRED_QUANTS):
            if q in fname:
                return idx
        return 999

    gguf_files.sort(key=quant_priority)
    return gguf_files[0]


def build_hf_model_entry(repo_data: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
    Converts a Hugging Face Hub model repository JSON object into a normalized
    catalog entry compatible with Argus PII Guard.
    """
    repo_id = repo_data.get("id") or repo_data.get("modelId")
    if not repo_id:
        return None

    siblings = repo_data.get("siblings", [])
    best_file = select_best_gguf_file(siblings) if siblings else None

    if best_file:
        filename = best_file.get("rfilename", "")
        file_size_bytes = best_file.get("size", 0)
    else:
        # If siblings were not populated, construct fallback standard GGUF name
        clean_name = repo_id.split("/")[-1]
        filename = f"{clean_name.lower()}-q4_k_m.gguf"
        file_size_bytes = 0

    quant = parse_model_quant(filename)
    params_b = parse_param_size(f"{repo_id} {filename}")

    if file_size_bytes and file_size_bytes > 0:
        size_gb = round(file_size_bytes / (1024 ** 3), 2)
    else:
        size_gb = estimate_size_gb(params_b, quant)

    tags = repo_data.get("tags", [])
    vision = detect_vision_capability(repo_id, tags)
    min_ram_gb, rec_ram_gb = estimate_ram_requirements(size_gb)

    # Clean display name
    clean_display = repo_id.split("/")[-1].replace("-GGUF", "").replace("-gguf", "")
    description = repo_data.get("description") or f"Hugging Face community model ({params_b}B params, {quant})."
    if vision:
        description += " Supports vision/multimodal inspection."

    downloads = repo_data.get("downloads", 0)
    likes = repo_data.get("likes", 0)

    return {
        "name": clean_display,
        "filename": filename,
        "params_b": params_b,
        "quant": quant,
        "size_gb": size_gb,
        "min_ram_gb": min_ram_gb,
        "rec_ram_gb": rec_ram_gb,
        "vision": vision,
        "description": description.strip(),
        "url": f"https://huggingface.co/{repo_id}",
        "download_url": f"https://huggingface.co/{repo_id}/resolve/main/{filename}",
        "repo_id": repo_id,
        "downloads": downloads,
        "likes": likes,
        "source": "huggingface",
    }


def fetch_hf_api_models(query_params: dict[str, Any], timeout: int = 6) -> list[dict[str, Any]]:
    """Executes a single search request against the Hugging Face REST API."""
    params = dict(query_params)
    params["full"] = "true"  # Ask for sibling files so we can inspect .gguf names
    query_str = urllib.parse.urlencode(params)
    url = f"{HF_MODELS_API}?{query_str}"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ArgusPIIGuard/1.0",
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status == 200:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list):
                return data
    return []


def query_huggingface_catalog(
    queries: Optional[list[dict[str, Any]]] = None,
    timeout: int = 6,
) -> list[dict[str, Any]]:
    """
    Executes multiple targeted queries against Hugging Face and aggregates parsed GGUF models.
    """
    if queries is None:
        queries = DEFAULT_HF_QUERIES

    discovered_models: list[dict[str, Any]] = []
    seen_repos: set[str] = set()

    for q in queries:
        try:
            results = fetch_hf_api_models(q, timeout=timeout)
            for repo in results:
                repo_id = repo.get("id") or repo.get("modelId")
                if not repo_id or repo_id in seen_repos:
                    continue
                seen_repos.add(repo_id)

                entry = build_hf_model_entry(repo)
                if entry:
                    discovered_models.append(entry)
        except Exception as e:
            logger.warning(f"Error querying Hugging Face with params {q}: {e}")

    return discovered_models


def load_cached_catalog(
    cache_path: Optional[str] = None,
    ttl_seconds: Optional[int] = DEFAULT_CACHE_TTL_SECONDS,
) -> Optional[list[dict[str, Any]]]:
    """
    Loads models from the disk cache if the file exists and is within TTL.
    If ttl_seconds is None, ignores expiration and returns whatever cached models exist.
    Returns None if cache is missing, corrupted, or expired.
    """
    path = Path(cache_path or HF_CACHE_FILE)
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        timestamp = data.get("timestamp", 0)
        models = data.get("models", [])

        is_valid_ttl = ttl_seconds is None or (time.time() - timestamp <= ttl_seconds)
        if is_valid_ttl and isinstance(models, list) and len(models) > 0:
            return models
    except Exception as e:
        logger.warning(f"Failed to read HF models cache from {path}: {e}")

    return None


def save_cached_catalog(
    models: list[dict[str, Any]],
    cache_path: Optional[str] = None,
) -> bool:
    """Saves model catalog with current timestamp to disk cache."""
    path = Path(cache_path or HF_CACHE_FILE)
    try:
        payload = {
            "timestamp": time.time(),
            "models": models,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        logger.warning(f"Failed to save HF models cache to {path}: {e}")
        return False


def merge_with_curated_catalog(
    dynamic_models: list[dict[str, Any]],
    curated_catalog: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Merges dynamic models from Hugging Face with the curated baseline catalog,
    ensuring baseline models take precedence while deduplicating by filename.
    """
    merged: list[dict[str, Any]] = []
    seen_filenames: set[str] = set()

    # Add curated models first
    for model in curated_catalog:
        entry = dict(model)
        entry["source"] = entry.get("source", "curated")
        fn = entry.get("filename", "").lower()
        if fn:
            seen_filenames.add(fn)
        merged.append(entry)

    # Add dynamic HF models that are not already present
    for model in dynamic_models:
        fn = model.get("filename", "").lower()
        if fn and fn in seen_filenames:
            continue
        if fn:
            seen_filenames.add(fn)
        merged.append(model)

    return merged


def get_dynamic_model_catalog(
    force_refresh: bool = False,
    cache_path: Optional[str] = None,
    curated_catalog: Optional[list[dict[str, Any]]] = None,
    timeout: int = 6,
) -> list[dict[str, Any]]:
    """
    Retrieves the complete model catalog:
    1. Checks local cache (unless force_refresh=True).
    2. If cache miss/expired, queries Hugging Face Hub API.
    3. Merges dynamic results with curated baseline models.
    4. Automatically falls back to cache or curated models on network error.
    """
    if curated_catalog is None:
        try:
            from .hardware_info import MODEL_CATALOG
            base_catalog = MODEL_CATALOG
        except ImportError:
            from backend.hardware_info import MODEL_CATALOG
            base_catalog = MODEL_CATALOG
    else:
        base_catalog = curated_catalog

    # Step 1: Check cache if not forcing refresh
    if not force_refresh:
        cached = load_cached_catalog(cache_path=cache_path)
        if cached:
            return merge_with_curated_catalog(cached, base_catalog)

    # Step 2: Query Hugging Face online
    try:
        dynamic_models = query_huggingface_catalog(timeout=timeout)
        if dynamic_models:
            save_cached_catalog(dynamic_models, cache_path=cache_path)
            return merge_with_curated_catalog(dynamic_models, base_catalog)
    except Exception as e:
        logger.warning(f"Hugging Face dynamic catalog fetch failed: {e}")

    # Step 3: Fallback — try reading any existing cache even if slightly stale
    stale_cache = load_cached_catalog(cache_path=cache_path, ttl_seconds=None)
    if stale_cache:
        return merge_with_curated_catalog(stale_cache, base_catalog)

    # Step 4: Ultimate fallback to static curated catalog
    return [dict(m, source="curated") for m in base_catalog]
