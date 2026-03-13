"""LLM Provider Router — Provider-agnostic LLM interface with auto-failover.

Supports: Ollama (default), OpenAI, Anthropic, Google Gemini, Groq, Cerebras.

Configuration via environment variables:
    LLM_PROVIDER: "auto" | "ollama" | "openai" | "anthropic" | "gemini" | "groq" | "cerebras"  (default: "auto")
    When set to "auto", selects the best free provider with automatic failover.
    OLLAMA_URL / OLLAMA_MODEL: for Ollama
    OPENAI_API_KEY / OPENAI_MODEL: for OpenAI (default model: gpt-4o-mini)
    ANTHROPIC_API_KEY / ANTHROPIC_MODEL: for Anthropic (default model: claude-3-haiku-20240307)
    GOOGLE_API_KEY / GOOGLE_MODEL: for Google Gemini (default model: gemini-1.5-flash)
    GROQ_API_KEY / GROQ_MODEL: for Groq (default model: llama-3.3-70b-versatile)
    CEREBRAS_API_KEY / CEREBRAS_MODEL: for Cerebras (default model: llama3.1-70b)
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

LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "auto").lower()

# ---------------------------------------------------------------------------
# Provider Failover Chain — tried in order when LLM_PROVIDER="auto"
# ---------------------------------------------------------------------------
# Free API providers first (no GPU needed), then Ollama (local/cloud GPU)
# Provider Failover Chain — tried in order when LLM_PROVIDER="auto"
# 1. Ultra-fast Free API providers (Groq/Cerebras/Lighthouse)
# 2. High-quality Free API (Gemini)
# 3. Local/Free GPU Platforms (Ollama)
# 4. Paid flagship providers (OpenAI/Anthropic) as final resort
PROVIDER_FAILOVER_CHAIN = ["groq", "cerebras", "lighthouse", "gemini", "ollama", "openai", "anthropic"]

# Map provider → (env_key_for_api_key, env_key_for_model, default_model, generate_fn_name)
PROVIDER_CONFIG = {
    "groq":      ("GROQ_API_KEY",      "GROQ_MODEL",      "llama-3.3-70b-versatile"),
    "cerebras":  ("CEREBRAS_API_KEY",   "CEREBRAS_MODEL",  "llama3.1-70b"),
    "openai":    ("OPENAI_API_KEY",     "OPENAI_MODEL",    "gpt-4o-mini"),
    "anthropic": ("ANTHROPIC_API_KEY",  "ANTHROPIC_MODEL", "claude-3-haiku-20240307"),
    "gemini":    ("GOOGLE_API_KEY",     "GOOGLE_MODEL",    "gemini-1.5-flash"),
    "lighthouse": ("LIGHTHOUSE_API_KEY", "LIGHTHOUSE_MODEL", "llama-3-70b-turbo"),
}

# Errors that trigger automatic failover (don't retry, move to next provider)
FAILOVER_STATUS_CODES = {
    401,  # Unauthorized (Invalid API Key)
    403,  # Forbidden (Blocked or no access)
    404,  # Not Found (Invalid model name or endpoint)
    413,  # Payload Too Large (Prompt exceeds context window)
    429,  # Rate-limited
    500,  # Internal Server Error
    502,  # Bad Gateway
    503,  # Overloaded
    504,  # Gateway Timeout
    529,  # Overloaded (Anthropic-specific)
}


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
        token_usage = {}
        for line in response.iter_lines():
            if line:
                chunk = json.loads(line)
                word = chunk.get("response", "")
                chunks.append(word)
                sys.stdout.write(word)
                sys.stdout.flush()
                
                if chunk.get("done", False):
                    token_usage["prompt_eval_count"] = chunk.get("prompt_eval_count", 0)
                    token_usage["eval_count"] = chunk.get("eval_count", 0)
        print()
        if token_usage:
            pt = token_usage.get("prompt_eval_count", 0)
            ct = token_usage.get("eval_count", 0)
            print(f"\n📊 [TOKEN USAGE] Prompt: {pt} | Generated: {ct} | Total: {pt + ct}\n")
        return "".join(chunks)
    else:
        resp = response.json()
        print(f"\n📊 [TOKEN USAGE] Prompt: {resp.get('prompt_eval_count', 0)} | Generated: {resp.get('eval_count', 0)}\n")
        return resp.get("response", "")


def _openai_compatible_generate(prompt: str, model: str, api_key: str,
                                 base_url: str, temperature: float,
                                 stream: bool) -> str:
    """Generate via any OpenAI-compatible Chat Completions API.

    Works with: OpenAI, Groq, Cerebras, Together.ai, Anyscale, etc.
    """
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
    if stream:
        payload["stream_options"] = {"include_usage": True}

    response = _retry_request(
        "POST", f"{base_url}/chat/completions",
        headers=headers, json=payload, timeout=300, stream=stream,
    )

    if stream:
        chunks: List[str] = []
        token_usage = None
        try:
            for line in response.iter_lines():
                if line:
                    line_str = line.decode("utf-8") if isinstance(line, bytes) else line
                    if line_str.startswith("data: "):
                        data = line_str[6:]
                        if data.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            
                            # Extract usage on final chunks
                            if "usage" in chunk and chunk["usage"] is not None:
                                token_usage = chunk["usage"]
                                
                            delta = chunk.get("choices", [{}])[0].get("delta", {}) if chunk.get("choices") else {}
                            word = delta.get("content", "")
                            if word:
                                chunks.append(word)
                                sys.stdout.write(word)
                                sys.stdout.flush()
                        except json.JSONDecodeError:
                            continue
        except requests.exceptions.ChunkedEncodingError:
            print("\n⚠️ Stream interrupted (Provider Rate Limit or Disconnect). Attempting failover...")
            raise requests.exceptions.HTTPError("Stream 429 Interruption")
            
        print()
        if token_usage:
            prompt_tok = token_usage.get("prompt_tokens", 0)
            comp_tok = token_usage.get("completion_tokens", 0)
            print(f"\n📊 [TOKEN USAGE] Prompt: {prompt_tok} | Generated: {comp_tok} | Total: {prompt_tok + comp_tok}\n")
            
        return "".join(chunks)
    else:
        resp_json = response.json()
        if "usage" in resp_json:
            u = resp_json["usage"]
            print(f"\n📊 [TOKEN USAGE] Prompt: {u.get('prompt_tokens', 0)} | Generated: {u.get('completion_tokens', 0)}\n")
        return resp_json["choices"][0]["message"]["content"]


def _openai_generate(prompt: str, model: str, api_key: str,
                     temperature: float, stream: bool) -> str:
    """Generate via OpenAI Chat Completions API."""
    return _openai_compatible_generate(
        prompt, model, api_key, "https://api.openai.com/v1",
        temperature, stream,
    )


def _groq_generate(prompt: str, model: str, api_key: str,
                   temperature: float, stream: bool) -> str:
    """Generate via Groq Cloud API (OpenAI-compatible, ~500 tok/s)."""
    
    # Auto-adjust massive models on Groq's super restricted free tiers to their ultra-fast API 
    if model == "llama-3.3-70b-versatile" and os.getenv("GROQ_MODEL") is None:
        model = "llama-3.1-8b-instant"
        
    return _openai_compatible_generate(
        prompt, model, api_key, "https://api.groq.com/openai/v1",
        temperature, stream,
    )


def _cerebras_generate(prompt: str, model: str, api_key: str,
                       temperature: float, stream: bool) -> str:
    """Generate via Cerebras Inference API (OpenAI-compatible, ~2000 tok/s)."""
    return _openai_compatible_generate(
        prompt, model, api_key, "https://api.cerebras.ai/v1",
        temperature, stream,
    )


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
    resp_json = response.json()
    blocks = resp_json.get("content", [])
    if "usage" in resp_json:
        u = resp_json["usage"]
        print(f"\n📊 [TOKEN USAGE] Prompt: {u.get('input_tokens', 0)} | Generated: {u.get('output_tokens', 0)}\n")
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
        token_usage = None
        for line in response.iter_lines():
            if line:
                line_str = line.decode("utf-8") if isinstance(line, bytes) else line
                if line_str.startswith("data: "):
                    data = line_str[6:]
                    try:
                        chunk = json.loads(data)
                        if "usageMetadata" in chunk:
                            token_usage = chunk["usageMetadata"]
                            
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
        if token_usage:
            prompt_tok = token_usage.get("promptTokenCount", 0)
            comp_tok = token_usage.get("candidatesTokenCount", 0)
            print(f"\n📊 [TOKEN USAGE] Prompt: {prompt_tok} | Generated: {comp_tok} | Total: {token_usage.get('totalTokenCount', 0)}\n")
        return "".join(chunks)
    else:
        resp_json = response.json()
        candidates = resp_json.get("candidates", [])
        if "usageMetadata" in resp_json:
            u = resp_json["usageMetadata"]
            print(f"\n📊 [TOKEN USAGE] Prompt: {u.get('promptTokenCount', 0)} | Generated: {u.get('candidatesTokenCount', 0)}\n")
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts)
        return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _call_provider(provider: str, prompt: str, temperature: float,
                   stream: bool, num_ctx: int) -> str:
    """Call a single provider. Raises on error (for failover to catch)."""
    if provider == "groq":
        api_key = os.getenv("GROQ_API_KEY", "")
        model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set")
        print(f"\U0001f916 [GROQ] model={model} (~500 tok/s)")
        return _groq_generate(prompt, model, api_key, temperature, stream)

    elif provider == "cerebras":
        api_key = os.getenv("CEREBRAS_API_KEY", "")
        # Updated to active valid Cerebras endpoint 
        model = os.getenv("CEREBRAS_MODEL", "llama3.1-8b")
        if not api_key:
            raise ValueError("CEREBRAS_API_KEY not set")
        print(f"\U0001f916 [CEREBRAS] model={model} (~2000 tok/s)")
        return _cerebras_generate(prompt, model, api_key, temperature, stream)

    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        # Robust check: skip if key is empty or a common placeholder used to trick validation
        if not api_key or api_key.lower() in ["not-needed", "empty", "your-key-here"]:
            raise ValueError("No valid OpenAI API key found. Skipping provider.")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        print(f"\U0001f916 [OPENAI] model={model}")
        return _openai_generate(prompt, model, api_key, temperature, stream)

    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        model = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        print(f"\U0001f916 [ANTHROPIC] model={model}")
        return _anthropic_generate(prompt, model, api_key, temperature)

    elif provider == "gemini":
        api_key = os.getenv("GOOGLE_API_KEY", "")
        model = os.getenv("GOOGLE_MODEL", "gemini-1.5-flash")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not set")
        print(f"\U0001f916 [GEMINI] model={model}")
        return _gemini_generate(prompt, model, api_key, temperature, stream)

    elif provider == "lighthouse":
        api_key = os.getenv("LIGHTHOUSE_API_KEY", "")
        model = os.getenv("LIGHTHOUSE_MODEL", "llama-3-70b-turbo")
        base_url = os.getenv("LIGHTHOUSE_URL", "https://api.lighthouse.ai/v1") # Placeholder
        if not api_key:
            raise ValueError("LIGHTHOUSE_API_KEY not set")
        print(f"\U0001f916 [LIGHTHOUSE] model={model}")
        return _openai_compatible_generate(prompt, model, api_key, base_url, temperature, stream)

    else:  # ollama
        ollama_url = os.getenv("OLLAMA_URL") or ""
        if not ollama_url:
            try:
                from scripts.gpu_platform import select_platform
                # Use failover=True to actually try to find a live free GPU platform (Colab, Kaggle, etc.)
                _, ollama_url = select_platform(use_failover=True)
            except Exception as e:
                print(f"DEBUG: GPU detection failed: {e}. Falling back to default.")
                ollama_url = "http://localhost:11434/api/generate"
        model = os.getenv("OLLAMA_MODEL") or "qwen2.5-coder:3b"
        print(f"\U0001f916 [OLLAMA] model={model} @ {ollama_url}")
        return _ollama_generate(prompt, model, ollama_url, temperature, num_ctx, stream)


def _is_failover_error(error: Exception) -> bool:
    """Check if an error should trigger automatic failover to the next provider."""
    if isinstance(error, requests.exceptions.HTTPError):
        if hasattr(error, 'response') and error.response is not None:
            return error.response.status_code in FAILOVER_STATUS_CODES
    if isinstance(error, (requests.exceptions.ConnectionError,
                          requests.exceptions.Timeout)):
        return True
    # Check for rate-limit messages in error text
    err_str = str(error).lower()
    return any(kw in err_str for kw in ["rate limit", "quota", "429", "503",
                                         "overloaded", "capacity"])


def generate(prompt: str, stream: bool = True, temperature: float = 0.2,
             num_ctx: int = 8192) -> str:
    """Provider-agnostic LLM generation with automatic failover.

    When LLM_PROVIDER="auto" (default):
      1. Detects available providers (checks which API keys are set)
      2. Tries them in priority order: groq → cerebras → gemini → openai → anthropic → ollama
      3. On rate-limit (429), timeout, or overload (503), auto-fails to the next provider

    When LLM_PROVIDER is set to a specific provider:
      1. Tries that provider first
      2. If it hits a rate limit or error, fails over through remaining providers
    """
    provider = os.getenv("LLM_PROVIDER", "auto").lower()

    # Start with the chosen provider, then failover through the rest
    if provider == "auto":
        chain = list(PROVIDER_FAILOVER_CHAIN)
    elif provider == "ollama":
        chain = ["ollama"]
    else:
        chain = [provider] + [p for p in PROVIDER_FAILOVER_CHAIN if p != provider]

    print(f"DEBUG: Active provider chain: {chain}")
    last_error = None
    for i, prov in enumerate(chain):
        # Pre-check for API keys
        if prov != "ollama":
            key_var = PROVIDER_CONFIG[prov][0]
            api_key = os.getenv(key_var)
            if not api_key:
                # print(f"DEBUG: Skipping {prov} (missing {key_var})")
                continue
            print(f"DEBUG: Attempting {prov} (key found)")

        try:
            return _call_provider(prov, prompt, temperature, stream, num_ctx)
        except ValueError as e:
            # This handles cases where _call_provider might still raise for missing keys
            continue
        except requests.exceptions.HTTPError as e:
            last_error = e
            if _is_failover_error(e) and i < len(chain) - 1:
                next_prov = chain[i + 1] if i + 1 < len(chain) else "ollama"
                status = e.response.status_code if e.response is not None else "unknown"
                print(f"\n\u26a0\ufe0f {prov.upper()} returned {status}. "
                      f"Failing over to {next_prov.upper()}...")
                continue
            else:
                print(f"\n\u274c LLM error ({prov}): {e}")
                return ""
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            last_error = e
            if i < len(chain) - 1:
                next_prov = chain[i + 1]
                print(f"\n\u26a0\ufe0f {prov.upper()} unreachable. "
                      f"Failing over to {next_prov.upper()}...")
                continue
            else:
                print(f"\n\u274c All providers failed. Last error ({prov}): {e}")
                return ""
        except Exception as e:
            last_error = e
            if _is_failover_error(e) and i < len(chain) - 1:
                next_prov = chain[i + 1]
                print(f"\n\u26a0\ufe0f {prov.upper()} error: {e}. "
                      f"Failing over to {next_prov.upper()}...")
                continue
            else:
                print(f"\n\u274c LLM generation error ({prov}): {e}")
                return ""

    # All providers exhausted
    print(f"\n\u274c All LLM providers exhausted. Last error: {last_error}")
    return ""


def get_provider_info() -> str:
    """Returns a human-readable string describing the active LLM provider."""
    provider = os.getenv("LLM_PROVIDER", "auto").lower()
    
    active = provider
    if provider == "auto":
        # Check failover chain for first available key
        active = "ollama" # Default
        for p in PROVIDER_FAILOVER_CHAIN:
            if p == "ollama":
                active = "ollama"
                break
            key_var = PROVIDER_CONFIG[p][0]
            if os.getenv(key_var):
                active = p
                break

    if active == "openai":
        return f"OpenAI ({os.getenv('OPENAI_MODEL', 'gpt-4o-mini')})"
    elif active == "anthropic":
        return f"Anthropic ({os.getenv('ANTHROPIC_MODEL', 'claude-3-haiku-20240307')})"
    elif active == "gemini":
        return f"Google Gemini ({os.getenv('GOOGLE_MODEL', 'gemini-1.5-flash')})"
    elif active == "groq":
        return f"Groq ({os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')})"
    elif active == "cerebras":
        return f"Cerebras ({os.getenv('CEREBRAS_MODEL', 'llama3.1-8b')})"
    elif active == "lighthouse":
        return f"Lighthouse ({os.getenv('LIGHTHOUSE_MODEL', 'llama-3-70b-turbo')})"
    else:
        return f"Ollama ({os.getenv('OLLAMA_MODEL', 'qwen2.5-coder:3b')})"
