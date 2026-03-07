"""GPU Platform Intelligence — Auto-detection with health-check failover.

Supports: Google Colab, Kaggle, Vast.ai, RunPod, Lightning.ai, HuggingFace,
Oracle Cloud, local Ollama, and any custom endpoint.

FAILOVER: If the primary GPU endpoint is down, automatically tries the next
configured platform in priority order.
"""
import os
import requests
from typing import Dict, Optional, Tuple, List

# ---------------------------------------------------------------------------
# Platform Registry
# ---------------------------------------------------------------------------
PLATFORMS: Dict[str, Dict] = {
    "local": {
        "name": "Local Ollama",
        "env_var": None,
        "description": "Default local Ollama instance (CPU or local GPU)",
        "free": True,
        "gpu": "Depends on host hardware",
    },
    "colab": {
        "name": "Google Colab (T4 via ngrok)",
        "env_var": "COLAB_OLLAMA_URL",
        "description": "Free T4 GPU (15GB VRAM), ~4-12 hrs/session",
        "free": True,
        "gpu": "NVIDIA T4 (15GB)",
    },
    "kaggle": {
        "name": "Kaggle Kernels (P100/T4)",
        "env_var": "KAGGLE_OLLAMA_URL",
        "description": "Free P100 or T4 GPU, 30 hrs/week",
        "free": True,
        "gpu": "NVIDIA P100/T4",
    },
    "lightning": {
        "name": "Lightning.ai",
        "env_var": "LIGHTNING_OLLAMA_URL",
        "description": "22 free GPU hours/month",
        "free": True,
        "gpu": "T4/A10G",
    },
    "huggingface": {
        "name": "Hugging Face Spaces (ZeroGPU)",
        "env_var": "HF_OLLAMA_URL",
        "description": "Free for public spaces with T4 ZeroGPU",
        "free": True,
        "gpu": "NVIDIA T4 (ZeroGPU shared)",
    },
    "sagemaker": {
        "name": "Amazon SageMaker Studio Lab",
        "env_var": "SAGEMAKER_OLLAMA_URL",
        "description": "Free T4 GPU, no credit card, 15GB persistent storage",
        "free": True,
        "gpu": "NVIDIA T4 (15GB)",
    },
    "paperspace": {
        "name": "Gradient by Paperspace",
        "env_var": "PAPERSPACE_OLLAMA_URL",
        "description": "Free GPU tier with limited hours",
        "free": True,
        "gpu": "Various (free tier)",
    },
    "oracle": {
        "name": "Oracle Cloud (Always Free A10)",
        "env_var": "ORACLE_OLLAMA_URL",
        "description": "Always-free tier with A10 GPU (limited availability)",
        "free": True,
        "gpu": "NVIDIA A10 (24GB)",
    },
    "vastai": {
        "name": "Vast.ai (RTX 3090/4090)",
        "env_var": "VASTAI_OLLAMA_URL",
        "description": "Cheapest GPU rental ($0.15-0.30/hr)",
        "free": False,
        "gpu": "RTX 3090/4090 (24GB)",
        "cost": "$0.15-0.30/hr",
    },
    "runpod": {
        "name": "RunPod Serverless",
        "env_var": "RUNPOD_OLLAMA_URL",
        "description": "Serverless GPU endpoints, pay per second",
        "free": False,
        "gpu": "A40/A100 (48-80GB)",
        "cost": "$0.39/hr (community cloud)",
    },
    "custom": {
        "name": "Custom Endpoint",
        "env_var": "CUSTOM_OLLAMA_URL",
        "description": "Any custom Ollama-compatible API endpoint",
        "free": None,
        "gpu": "User-defined",
    },
}

# Failover priority: free platforms first, then paid
FAILOVER_ORDER: List[str] = [
    "colab", "kaggle", "lightning", "huggingface", "sagemaker",
    "paperspace", "oracle", "vastai", "runpod", "custom",
]


def _resolve_url(base_url: str) -> str:
    """Ensures the URL ends with /api/generate."""
    resolved = base_url.rstrip("/")
    if not resolved.endswith("/api/generate"):
        resolved += "/api/generate"
    return resolved


def health_check(url: str, timeout: int = 5) -> bool:
    """Checks if an Ollama endpoint is alive and responding."""
    try:
        # Hit the /api/tags endpoint (lightweight) to check health
        tags_url = url.replace("/api/generate", "/api/tags")
        resp = requests.get(tags_url, timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def detect_platform() -> Tuple[str, str]:
    """Auto-detects the best available GPU platform from environment variables.

    Returns (platform_key, resolved_url).
    Priority: explicit OLLAMA_URL > platform-specific env vars > local.
    """
    # 1. Explicit override
    explicit_url = os.getenv("OLLAMA_URL", "")
    if explicit_url and "localhost" not in explicit_url and "127.0.0.1" not in explicit_url:
        return "custom", explicit_url

    # 2. Check platform-specific env vars in failover order
    for platform_key in FAILOVER_ORDER:
        env_var = PLATFORMS[platform_key].get("env_var")
        if env_var:
            url = os.getenv(env_var)
            if url:
                resolved = _resolve_url(url)
                print(f"[GPU] Detected: {PLATFORMS[platform_key]['name']}")
                print(f"[GPU] GPU: {PLATFORMS[platform_key]['gpu']}")
                return platform_key, resolved

    # 3. Default
    return "local", "http://localhost:11434/api/generate"


def detect_with_failover() -> Tuple[str, str]:
    """Detects the best platform AND verifies it is alive.

    If the primary platform is down, tries the next one in FAILOVER_ORDER.
    Falls back to local Ollama as last resort.
    """
    # 1. Explicit override (no failover — user knows what they want)
    explicit_url = os.getenv("OLLAMA_URL", "")
    if explicit_url and "localhost" not in explicit_url and "127.0.0.1" not in explicit_url:
        return "custom", explicit_url

    # 2. Try each configured platform with a health check
    tried: List[str] = []
    for platform_key in FAILOVER_ORDER:
        env_var = PLATFORMS[platform_key].get("env_var")
        if not env_var:
            continue
        url = os.getenv(env_var)
        if not url:
            continue

        resolved = _resolve_url(url)
        tried.append(platform_key)
        print(f"[GPU] Trying {PLATFORMS[platform_key]['name']}...")

        if health_check(resolved):
            print(f"[GPU] Connected: {PLATFORMS[platform_key]['name']} ({PLATFORMS[platform_key]['gpu']})")
            return platform_key, resolved
        else:
            print(f"[GPU] {PLATFORMS[platform_key]['name']} is DOWN. Trying next...")

    # 3. Fallback to local
    if tried:
        print(f"[GPU] All remote platforms down ({', '.join(tried)}). Falling back to local Ollama.")
    return "local", "http://localhost:11434/api/generate"


def get_platform_info(platform_key: str) -> Dict:
    """Returns metadata about a platform."""
    return PLATFORMS.get(platform_key, PLATFORMS["local"])


def list_platforms() -> str:
    """Returns a formatted string listing all supported platforms."""
    lines = ["Supported GPU Platforms:\n"]
    for key, info in PLATFORMS.items():
        cost = "FREE" if info.get("free") else info.get("cost", "Paid")
        lines.append(f"  [{key:12s}] {info['name']:35s} | GPU: {info['gpu']:25s} | {cost}")
    return "\n".join(lines)


def select_platform(use_failover: bool = True) -> Tuple[str, str]:
    """Main entry point: detects and returns (platform_key, ollama_url).

    Args:
        use_failover: If True, performs health checks and falls back to next
                      platform if the primary is down. If False, returns the
                      first configured platform without checking.
    """
    gpu_platform = os.getenv("GPU_PLATFORM", "auto")

    if gpu_platform != "auto" and gpu_platform in PLATFORMS:
        env_var = PLATFORMS[gpu_platform].get("env_var")
        url = os.getenv(env_var, "http://localhost:11434/api/generate") if env_var else "http://localhost:11434/api/generate"
        print(f"[GPU] Manually selected: {PLATFORMS[gpu_platform]['name']}")
        return gpu_platform, url

    if use_failover:
        return detect_with_failover()
    return detect_platform()


if __name__ == "__main__":
    print(list_platforms())
    print()
    platform, url = select_platform()
    print(f"\nSelected: {platform} -> {url}")
