"""GPU Scheduler — Smart platform selector with budget awareness.

Checks all configured GPU platforms in priority order:
1. Google Colab (free, unlimited sessions)
2. Kaggle (free, 30 GPU hrs/week)
3. Oracle Cloud (SGD 400 credits, Terraform auto-provision)
4. Local CPU fallback

Usage:
    python scripts/gpu_scheduler.py                  # Auto-detect best platform
    python scripts/gpu_scheduler.py --provision       # Auto-provision Oracle if needed
    python scripts/gpu_scheduler.py --status           # Show all platform status
"""
import os
import sys
import time
import subprocess
import json
from typing import Optional, Tuple, Dict, List

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from scripts.gpu_platform import (
    PLATFORMS, FAILOVER_ORDER, health_check, _resolve_url,
    detect_platform, detect_with_failover, select_platform,
    get_platform_info, list_platforms,
)

# ---------------------------------------------------------------------------
# Platform Priority (free first, then paid)
# ---------------------------------------------------------------------------
FREE_PRIORITY: List[str] = ["colab", "kaggle", "lightning", "huggingface", "sagemaker"]
PAID_PRIORITY: List[str] = ["oracle"]
TERRAFORM_DIR: str = os.path.join(os.path.dirname(__file__), "..", "infra", "oracle")


def check_platform_health(platform_key: str) -> Tuple[bool, str]:
    """Checks if a specific platform is configured and healthy."""
    info = PLATFORMS.get(platform_key, {})
    env_var = info.get("env_var")

    if not env_var:
        if platform_key == "local":
            url = "http://localhost:11434/api/generate"
            alive = health_check(url)
            return alive, url if alive else ""
        return False, ""

    url = os.getenv(env_var, "")
    if not url:
        return False, ""

    resolved = _resolve_url(url)
    alive = health_check(resolved)
    return alive, resolved if alive else ""


def get_all_platform_status() -> List[Dict]:
    """Returns health status of all configured platforms."""
    statuses = []
    for key in ["colab", "kaggle", "oracle", "lightning", "huggingface",
                 "sagemaker", "paperspace", "local"]:
        info = PLATFORMS.get(key, {})
        env_var = info.get("env_var", "")
        configured = bool(os.getenv(env_var, "")) if env_var else (key == "local")
        alive = False
        url = ""

        if configured:
            alive, url = check_platform_health(key)

        statuses.append({
            "platform": key,
            "name": info.get("name", key),
            "configured": configured,
            "alive": alive,
            "url": url,
            "free": info.get("free", False),
            "gpu": info.get("gpu", "Unknown"),
        })
    return statuses


def print_status_table(statuses: List[Dict]) -> None:
    """Pretty prints platform status table."""
    print("\n" + "=" * 80)
    print("  GPU Platform Status")
    print("=" * 80)
    print(f"  {'Platform':<15} {'Status':<12} {'Free':<6} {'GPU':<25} {'URL'}")
    print("-" * 80)

    for s in statuses:
        if s["alive"]:
            status = "✅ LIVE"
        elif s["configured"]:
            status = "❌ DOWN"
        else:
            status = "⬜ N/A"

        free = "FREE" if s["free"] else "PAID"
        url_display = s["url"][:40] + "..." if len(s["url"]) > 40 else s["url"]
        print(f"  {s['platform']:<15} {status:<12} {free:<6} {s['gpu']:<25} {url_display}")

    print("=" * 80)


def select_best_platform(allow_provision: bool = False) -> Tuple[str, str]:
    """Selects the best available GPU platform in smart priority order.

    Priority:
    1. Free platforms (Colab > Kaggle > Lightning > HuggingFace > SageMaker)
    2. Oracle Cloud (if credits available and provisioning allowed)
    3. Local Ollama

    Args:
        allow_provision: If True, will terraform apply Oracle if no free platform is alive.

    Returns:
        (platform_key, ollama_url)
    """
    print("\n🔍 Scanning GPU platforms...")

    # 1. Check free platforms first
    for key in FREE_PRIORITY:
        alive, url = check_platform_health(key)
        if alive:
            info = PLATFORMS[key]
            print(f"✅ Using {info['name']} ({info['gpu']}) — FREE")
            return key, url

    print("⚠️  No free GPU platforms available.")

    # 2. Check Oracle Cloud
    alive, url = check_platform_health("oracle")
    if alive:
        info = PLATFORMS["oracle"]
        print(f"✅ Using {info['name']} ({info['gpu']}) — FROM CREDITS")
        return "oracle", url

    # 3. Auto-provision Oracle if allowed
    if allow_provision:
        print("🏗️  Attempting to provision Oracle Cloud GPU via Terraform...")
        url = provision_oracle()
        if url:
            return "oracle", url

    # 4. Fallback to local
    alive, url = check_platform_health("local")
    if alive:
        print("✅ Using Local Ollama (CPU mode)")
        return "local", url

    print("❌ No GPU platforms available. Start Ollama locally or configure a cloud platform.")
    return "local", "http://localhost:11434/api/generate"


def provision_oracle() -> Optional[str]:
    """Provisions an Oracle Cloud GPU VM via Terraform.

    Returns the Ollama URL if successful, None otherwise.
    """
    tf_dir = os.path.abspath(TERRAFORM_DIR)

    if not os.path.exists(os.path.join(tf_dir, "main.tf")):
        print(f"❌ Terraform files not found at {tf_dir}")
        return None

    # 1. Budget check
    budget_script = os.path.join(tf_dir, "budget_check.sh")
    if os.path.exists(budget_script):
        print("💰 Running budget check...")
        result = subprocess.run(["bash", budget_script], cwd=tf_dir)
        if result.returncode != 0:
            print("❌ Budget check failed. Not provisioning.")
            return None

    # 2. Terraform init + apply
    print("🔧 Running terraform init...")
    result = subprocess.run(
        ["terraform", "init", "-no-color"],
        cwd=tf_dir, capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"❌ Terraform init failed: {result.stderr[:200]}")
        return None

    print("🚀 Running terraform apply (this takes ~3-5 minutes)...")
    result = subprocess.run(
        ["terraform", "apply", "-auto-approve", "-no-color"],
        cwd=tf_dir, capture_output=True, text=True, timeout=600
    )
    if result.returncode != 0:
        print(f"❌ Terraform apply failed: {result.stderr[:200]}")
        return None

    # 3. Get the output URL
    result = subprocess.run(
        ["terraform", "output", "-json"],
        cwd=tf_dir, capture_output=True, text=True
    )
    if result.returncode == 0:
        try:
            outputs = json.loads(result.stdout)
            url = outputs.get("ollama_url", {}).get("value", "")
            if url:
                print(f"✅ Oracle GPU provisioned! URL: {url}")

                # 4. Start auto-destroy timer in background
                auto_destroy = os.path.join(tf_dir, "auto_destroy.sh")
                if os.path.exists(auto_destroy):
                    subprocess.Popen(
                        ["bash", auto_destroy],
                        cwd=tf_dir,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    print("⏱️  Auto-destroy timer started in background")

                # 5. Wait for Ollama to be ready on the VM
                print("⏳ Waiting for Ollama to be ready on the VM...")
                for i in range(60):
                    if health_check(url):
                        print("✅ Ollama is responding!")
                        # Set environment variable for the pipeline
                        os.environ["ORACLE_OLLAMA_URL"] = url.replace("/api/generate", "")
                        return url
                    time.sleep(10)
                    if i % 6 == 0:
                        print(f"   Still waiting... ({i*10}s)")

                print("⚠️  VM provisioned but Ollama not responding yet. Try again in a few minutes.")
                return url
        except (json.JSONDecodeError, KeyError):
            pass

    print("❌ Could not retrieve Ollama URL from Terraform outputs.")
    return None


def destroy_oracle() -> bool:
    """Destroys the Oracle Cloud GPU VM via Terraform."""
    tf_dir = os.path.abspath(TERRAFORM_DIR)

    if not os.path.exists(os.path.join(tf_dir, "main.tf")):
        print("❌ No Terraform files found.")
        return False

    print("🗑️  Destroying Oracle Cloud GPU VM...")
    result = subprocess.run(
        ["terraform", "destroy", "-auto-approve", "-no-color"],
        cwd=tf_dir, capture_output=True, text=True, timeout=300
    )
    if result.returncode == 0:
        print("✅ All Oracle Cloud resources destroyed. Billing stopped.")
        return True
    else:
        print(f"❌ Terraform destroy failed: {result.stderr[:200]}")
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="GPU Platform Scheduler")
    parser.add_argument("--status", action="store_true", help="Show all platform statuses")
    parser.add_argument("--provision", action="store_true", help="Auto-provision Oracle if needed")
    parser.add_argument("--destroy", action="store_true", help="Destroy Oracle Cloud resources")
    parser.add_argument("--export", action="store_true", help="Export selected URL as env var")
    args = parser.parse_args()

    if args.status:
        statuses = get_all_platform_status()
        print_status_table(statuses)
        return

    if args.destroy:
        destroy_oracle()
        return

    platform, url = select_best_platform(allow_provision=args.provision)

    if args.export:
        # Print export command for shell eval
        env_var = PLATFORMS.get(platform, {}).get("env_var", "OLLAMA_URL")
        if not env_var:
            env_var = "OLLAMA_URL"
        print(f'export {env_var}="{url.replace("/api/generate", "")}"')
        print(f'export OLLAMA_URL="{url}"')
    else:
        print(f"\n🎯 Selected: {platform} → {url}")


if __name__ == "__main__":
    main()
