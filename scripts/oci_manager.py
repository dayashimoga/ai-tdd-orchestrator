"""OCI Manager — Helper for interacting with Oracle Cloud Infrastructure.

Provides credit detection and instance status checks.
"""
import os
import subprocess
import json
from typing import Optional, Dict

def check_oci_credits() -> float:
    """Checks the available OCI credit balance.
    
    Priority:
    1. OCI_CREDITS_AVAILABLE env var (explicit manual override)
    2. OCI CLI (querying subscription info)
    
    Returns:
        Available credits as a float (defaulting to 0.0 if unknown).
    """
    # 1. Manual override for testing/CI
    env_credits = os.getenv("OCI_CREDITS_AVAILABLE")
    if env_credits is not None:
        try:
            return float(env_credits) if env_credits.lower() != "true" else 400.0
        except ValueError:
            return 400.0 if env_credits.lower() == "true" else 0.0

    # 2. Try OCI CLI
    try:
        # Check if oci command exists
        subprocess.run(["oci", "--version"], capture_output=True, check=True)
        
        # Query subscriptions
        result = subprocess.run(
            ["oci", "account", "subscription", "list", "--output", "json"],
            capture_output=True, text=True, check=True
        )
        data = json.loads(result.stdout)
        
        # Extract available balance (usually from the first summary item)
        if data.get("data") and len(data["data"]) > 0:
            balance = data["data"][0].get("available-credit-amount", 0.0)
            return float(balance)
    except Exception:
        # If CLI fails or no credits found, return 0.0
        pass

    return 0.0

def is_oci_provisioned() -> bool:
    """Checks if our OCI compute instance is already running."""
    url = os.getenv("ORACLE_OLLAMA_URL")
    if not url:
        return False
    
    # We can perform a lightweight health check if the URL is set
    try:
        import requests
        tags_url = url.rstrip("/")
        if not tags_url.endswith("/api/tags"):
            tags_url += "/api/tags"
        resp = requests.get(tags_url, timeout=2)
        return resp.status_code == 200
    except Exception:
        return False

if __name__ == "__main__":
    print(f"OCI Credits: {check_oci_credits()}")
    print(f"OCI Provisioned: {is_oci_provisioned()}")
