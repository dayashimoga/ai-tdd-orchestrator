"""LLM Provider Router — Provider-agnostic LLM interface.

Supports: Ollama (default), OpenAI, Anthropic, Google Gemini.

Configuration via environment variables:
    LLM_PROVIDER: "ollama" | "openai" | "anthropic" | "gemini"  (default: "ollama")
    OLLAMA_URL / OLLAMA_MODEL: for Ollama
    OPENAI_API_KEY / OPENAI_MODEL: for OpenAI (default model: gpt-4o-mini)
    ANTHROPIC_API_KEY / ANTHROPIC_MODEL: for Anthropic (default model: claude-3-haiku-20240307)
    GOOGLE_API_KEY / GOOGLE_MODEL: for Google Gemini (default model: gemini-1.5-flash)
"""
import json
import os
import sys
import time
from typing import Optional, List

import requests

# ---------------------------------------------------------------------------
# Connection Pooling (O1) — Reuses TCP connections across LLM calls
# ---------------------------------------------------------------------------
_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    """Returns a singleton requests.Session for connection pooling."""
    global _session
    if _session is None:
        _session = requests.Session()
        # Configure connection pool size for parallel calls
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=4,
            pool_maxsize=10,
            max_retries=0,  # We handle retries ourselves
        )
        _session.mount("http://", adapter)
        _session.mount("https://", adapter)
    return _session


# ---------------------------------------------------------------------------
# Retry with Exponential Backoff (CG2)
# ---------------------------------------------------------------------------
MAX_RETRIES: int = 3
BACKOFF_BASE: float = 0.5  # seconds


def _retry_request(method: str, url: str, max_retries: int = MAX_RETRIES,
                   **kwargs) -> requests.Response:
    """Executes an HTTP request with exponential backoff on transient errors.

    Retries on connection errors and 5xx server errors.
    """
    session = _get_session()
    last_error: Optional[Exception] = None

    for attempt in range(max_retries):
        try:
            if method == "POST":
                response = session.post(url, **kwargs)
            else:
                response = session.get(url, **kwargs)

            # Retry on server errors (5xx)
            if response.status_code >= 500 and attempt < max_retries - 1:
                delay = BACKOFF_BASE * (2 ** attempt)
                print(f"⚠️ Server error {response.status_code}, retrying in {delay:.1f}s...")
                time.sleep(delay)
                continue

            response.raise_for_status()
            return response
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            last_error = e
            if attempt < max_retries - 1:
                delay = BACKOFF_BASE * (2 ** attempt)
                print(f"⚠️ Connection error, retrying in {delay:.1f}s... ({e})")
                time.sleep(delay)
            else:
                raise
        except requests.exceptions.HTTPError:
            raise  # Non-5xx HTTP errors should not be retried

    raise last_error  # pragma: no cover


# ---------------------------------------------------------------------------
# Provider Registry
# ---------------------------------------------------------------------------

LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama").lower()


def _ollama_generate(prompt: str, model: str, base_url: str,
                     temperature: float, num_ctx: int, stream: bool) -> str:
    """Generate via Ollama /api/generate endpoint."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": stream,
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }
    response = _retry_request("POST", base_url, json=payload, timeout=300, stream=stream)

    if stream:
        chunks: List[str] = []
        for line in response.iter_lines():
            if line:
                chunk = json.loads(line)
                word = chunk.get("response", "")
                chunks.append(word)
                sys.stdout.write(word)
                sys.stdout.flush()
        print()
        return "".join(chunks)
    else:
        return response.json().get("response", "")


def _openai_generate(prompt: str, model: str, api_key: str,
                     temperature: float, stream: bool) -> str:
    """Generate via OpenAI Chat Completions API."""
    session = _get_session()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "stream": stream,
    }
    response = _retry_request(
        "POST", "https://api.openai.com/v1/chat/completions",
        headers=headers, json=payload, timeout=300, stream=stream,
    )

    if stream:
        chunks: List[str] = []
        for line in response.iter_lines():
            if line:
                line_str = line.decode("utf-8") if isinstance(line, bytes) else line
                if line_str.startswith("data: "):
                    data = line_str[6:]
                    if data.strip() == "[DONE]":
                        break
                    chunk = json.loads(data)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    word = delta.get("content", "")
                    if word:
                        chunks.append(word)
                        sys.stdout.write(word)
                        sys.stdout.flush()
        print()
        return "".join(chunks)
    else:
        return response.json()["choices"][0]["message"]["content"]


def _anthropic_generate(prompt: str, model: str, api_key: str,
                        temperature: float) -> str:
    """Generate via Anthropic Messages API."""
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }
    response = _retry_request(
        "POST", "https://api.anthropic.com/v1/messages",
        headers=headers, json=payload, timeout=300,
    )
    blocks = response.json().get("content", [])
    return "".join(b.get("text", "") for b in blocks)


def _gemini_generate(prompt: str, model: str, api_key: str,
                     temperature: float, stream: bool = False) -> str:
    """Generate via Google Gemini REST API with optional streaming (E5)."""
    if stream:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?key={api_key}&alt=sse"
    else:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    }
    response = _retry_request("POST", url, json=payload, timeout=300, stream=stream)

    if stream:
        chunks: List[str] = []
        for line in response.iter_lines():
            if line:
                line_str = line.decode("utf-8") if isinstance(line, bytes) else line
                if line_str.startswith("data: "):
                    data = line_str[6:]
                    try:
                        chunk = json.loads(data)
                        candidates = chunk.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            for p in parts:
                                word = p.get("text", "")
                                if word:
                                    chunks.append(word)
                                    sys.stdout.write(word)
                                    sys.stdout.flush()
                    except json.JSONDecodeError:
                        continue
        print()
        return "".join(chunks)
    else:
        candidates = response.json().get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts)
        return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate(prompt: str, stream: bool = True, temperature: float = 0.2,
             num_ctx: int = 8192) -> str:
    """Provider-agnostic LLM generation.

    Routes to the correct backend based on LLM_PROVIDER env var.
    Falls back to Ollama if no provider is configured.
    """
    provider = LLM_PROVIDER

    try:
        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY", "")
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            if not api_key:
                print("❌ OPENAI_API_KEY not set. Falling back to Ollama.")
                provider = "ollama"
            else:
                print(f"🤖 [{provider.upper()}] model={model}")
                return _openai_generate(prompt, model, api_key, temperature, stream)

        if provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            model = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
            if not api_key:
                print("❌ ANTHROPIC_API_KEY not set. Falling back to Ollama.")
                provider = "ollama"
            else:
                print(f"🤖 [{provider.upper()}] model={model}")
                return _anthropic_generate(prompt, model, api_key, temperature)

        if provider == "gemini":
            api_key = os.getenv("GOOGLE_API_KEY", "")
            model = os.getenv("GOOGLE_MODEL", "gemini-1.5-flash")
            if not api_key:
                print("❌ GOOGLE_API_KEY not set. Falling back to Ollama.")
                provider = "ollama"
            else:
                print(f"🤖 [{provider.upper()}] model={model}")
                return _gemini_generate(prompt, model, api_key, temperature, stream)

        # Default: Ollama — use lazy platform detection (PS2)
        ollama_url = os.getenv("OLLAMA_URL") or ""
        if not ollama_url:
            try:
                from scripts.gpu_platform import select_platform
                _, ollama_url = select_platform(use_failover=False)
            except Exception:
                ollama_url = "http://localhost:11434/api/generate"
        model = os.getenv("OLLAMA_MODEL") or "qwen2.5-coder:3b"
        print(f"🤖 [OLLAMA] model={model}")
        return _ollama_generate(prompt, model, ollama_url, temperature, num_ctx, stream)

    except Exception as e:
        print(f"\n❌ LLM generation error ({provider}): {e}")
        return ""


def get_provider_info() -> str:
    """Returns a human-readable string describing the active LLM provider."""
    provider = LLM_PROVIDER
    if provider == "openai":
        return f"OpenAI ({os.getenv('OPENAI_MODEL', 'gpt-4o-mini')})"
    elif provider == "anthropic":
        return f"Anthropic ({os.getenv('ANTHROPIC_MODEL', 'claude-3-haiku-20240307')})"
    elif provider == "gemini":
        return f"Google Gemini ({os.getenv('GOOGLE_MODEL', 'gemini-1.5-flash')})"
    else:
        return f"Ollama ({os.getenv('OLLAMA_MODEL', 'qwen2.5-coder:3b')})"
