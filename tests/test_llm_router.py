"""Tests for scripts/llm_router.py"""
import os
import json
import time
from unittest.mock import patch, MagicMock, PropertyMock
import pytest
import requests
from scripts.llm_router import (
    _ollama_generate, _openai_generate, _anthropic_generate,
    _gemini_generate, generate, get_provider_info,
    _get_session, _retry_request,
)
import scripts.llm_router as llm_router


class TestSessionPooling:
    """Tests for connection pooling via requests.Session (O1)."""

    def test_get_session_returns_session(self):
        llm_router._session = None
        session = _get_session()
        assert isinstance(session, requests.Session)
        # Cleanup
        llm_router._session = None

    def test_get_session_singleton(self):
        llm_router._session = None
        s1 = _get_session()
        s2 = _get_session()
        assert s1 is s2
        llm_router._session = None


class TestRetryRequest:
    """Tests for exponential backoff retry (CG2)."""

    @patch.object(requests.Session, 'post')
    def test_retry_success_first_try(self, mock_post):
        llm_router._session = None
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp
        result = _retry_request("POST", "http://test.com", json={}, timeout=10)
        assert result.status_code == 200
        llm_router._session = None

    @patch.object(requests.Session, 'post')
    def test_retry_on_connection_error(self, mock_post):
        llm_router._session = None
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_post.side_effect = [
            requests.exceptions.ConnectionError("refused"),
            mock_resp,
        ]
        with patch('time.sleep'):
            result = _retry_request("POST", "http://test.com", max_retries=2, json={}, timeout=10)
        assert result.status_code == 200
        llm_router._session = None

    @patch.object(requests.Session, 'post')
    def test_retry_exhausted(self, mock_post):
        llm_router._session = None
        mock_post.side_effect = requests.exceptions.ConnectionError("refused")
        with patch('time.sleep'):
            with pytest.raises(requests.exceptions.ConnectionError):
                _retry_request("POST", "http://test.com", max_retries=2, json={}, timeout=10)
        llm_router._session = None

    @patch.object(requests.Session, 'post')
    def test_retry_on_5xx(self, mock_post):
        llm_router._session = None
        mock_resp_500 = MagicMock()
        mock_resp_500.status_code = 500
        mock_resp_200 = MagicMock()
        mock_resp_200.status_code = 200
        mock_resp_200.raise_for_status = MagicMock()
        mock_post.side_effect = [mock_resp_500, mock_resp_200]
        with patch('time.sleep'):
            result = _retry_request("POST", "http://test.com", max_retries=2, json={}, timeout=10)
        assert result.status_code == 200
        llm_router._session = None

    @patch.object(requests.Session, 'get')
    def test_retry_get_method(self, mock_get):
        llm_router._session = None
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp
        result = _retry_request("GET", "http://test.com", timeout=10)
        assert result.status_code == 200
        llm_router._session = None

    @patch.object(requests.Session, 'post')
    def test_retry_http_error_no_retry(self, mock_post):
        llm_router._session = None
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("Bad Request")
        mock_post.return_value = mock_resp
        with pytest.raises(requests.exceptions.HTTPError):
            _retry_request("POST", "http://test.com", json={}, timeout=10)
        llm_router._session = None


class TestOllamaGenerate:
    @patch("scripts.llm_router._retry_request")
    def test_ollama_stream(self, mock_retry):
        mock_resp = MagicMock()
        mock_resp.iter_lines.return_value = [
            json.dumps({"response": "Hello "}).encode(),
            json.dumps({"response": "World"}).encode(),
        ]
        mock_retry.return_value = mock_resp
        result = _ollama_generate("test", "qwen", "http://localhost/api/generate", 0.2, 8192, True)
        assert result == "Hello World"

    @patch("scripts.llm_router._retry_request")
    def test_ollama_no_stream(self, mock_retry):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "Generated code"}
        mock_retry.return_value = mock_resp
        result = _ollama_generate("test", "qwen", "http://localhost/api/generate", 0.2, 8192, False)
        assert result == "Generated code"


class TestOpenAIGenerate:
    @patch("scripts.llm_router._retry_request")
    def test_openai_no_stream(self, mock_retry):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "OpenAI response"}}]
        }
        mock_retry.return_value = mock_resp
        result = _openai_generate("test", "gpt-4o-mini", "key123", 0.2, False)
        assert result == "OpenAI response"

    @patch("scripts.llm_router._retry_request")
    def test_openai_stream(self, mock_retry):
        mock_resp = MagicMock()
        mock_resp.iter_lines.return_value = [
            b"data: " + json.dumps({"choices": [{"delta": {"content": "Stream "}}]}).encode(),
            b"data: " + json.dumps({"choices": [{"delta": {"content": "Result"}}]}).encode(),
            b"data: [DONE]"
        ]
        mock_retry.return_value = mock_resp
        result = _openai_generate("test", "gpt-4o", "key123", 0.2, True)
        assert result == "Stream Result"


class TestAnthropicGenerate:
    @patch("scripts.llm_router._retry_request")
    def test_anthropic(self, mock_retry):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "content": [{"type": "text", "text": "Claude response"}]
        }
        mock_retry.return_value = mock_resp
        result = _anthropic_generate("test", "claude-3-haiku", "key123", 0.2)
        assert result == "Claude response"


class TestGeminiGenerate:
    @patch("scripts.llm_router._retry_request")
    def test_gemini_no_stream(self, mock_retry):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Gemini response"}]}}]
        }
        mock_retry.return_value = mock_resp
        result = _gemini_generate("test", "gemini-1.5-flash", "key123", 0.2, stream=False)
        assert result == "Gemini response"

    @patch("scripts.llm_router._retry_request")
    def test_gemini_no_candidates(self, mock_retry):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"candidates": []}
        mock_retry.return_value = mock_resp
        result = _gemini_generate("test", "gemini-1.5-flash", "key123", 0.2, stream=False)
        assert result == ""

    @patch("scripts.llm_router._retry_request")
    def test_gemini_stream(self, mock_retry):
        """E5: Test Gemini streaming via SSE."""
        mock_resp = MagicMock()
        mock_resp.iter_lines.return_value = [
            b"data: " + json.dumps({"candidates": [{"content": {"parts": [{"text": "Hello "}]}}]}).encode(),
            b"data: " + json.dumps({"candidates": [{"content": {"parts": [{"text": "World"}]}}]}).encode(),
        ]
        mock_retry.return_value = mock_resp
        result = _gemini_generate("test", "gemini-1.5-flash", "key123", 0.2, stream=True)
        assert result == "Hello World"

    @patch("scripts.llm_router._retry_request")
    def test_gemini_stream_bad_json(self, mock_retry):
        """Test Gemini streaming handles bad JSON gracefully."""
        mock_resp = MagicMock()
        mock_resp.iter_lines.return_value = [
            b"data: not-valid-json",
            b"data: " + json.dumps({"candidates": [{"content": {"parts": [{"text": "OK"}]}}]}).encode(),
        ]
        mock_retry.return_value = mock_resp
        result = _gemini_generate("test", "gemini-1.5-flash", "key123", 0.2, stream=True)
        assert result == "OK"


class TestGenerate:
    @patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}, clear=False)
    @patch("scripts.llm_router._retry_request")
    def test_generate_ollama_default(self, mock_retry):
        mock_resp = MagicMock()
        mock_resp.iter_lines.return_value = [json.dumps({"response": "OK"}).encode()]
        mock_retry.return_value = mock_resp
        llm_router.LLM_PROVIDER = "ollama"
        result = llm_router.generate("test prompt", stream=True)
        assert result == "OK"

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "gpt-4o"}, clear=False)
    @patch("scripts.llm_router._retry_request")
    def test_generate_openai(self, mock_retry):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "OpenAI via router"}}]
        }
        mock_retry.return_value = mock_resp
        llm_router.LLM_PROVIDER = "openai"
        result = llm_router.generate("test prompt", stream=False)
        assert result == "OpenAI via router"
        llm_router.LLM_PROVIDER = "ollama"

    @patch.dict(os.environ, {"OPENAI_API_KEY": "", "LLM_PROVIDER": "openai"}, clear=False)
    @patch("scripts.llm_router._retry_request")
    def test_generate_openai_fallback(self, mock_retry):
        mock_resp = MagicMock()
        mock_resp.iter_lines.return_value = [json.dumps({"response": "Falling back to Ollama"}).encode()]
        mock_retry.return_value = mock_resp
        llm_router.LLM_PROVIDER = "openai"
        result = llm_router.generate("test prompt", stream=True)
        assert result == "Falling back to Ollama"
        llm_router.LLM_PROVIDER = "ollama"

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=False)
    @patch("scripts.llm_router._retry_request")
    def test_generate_anthropic(self, mock_retry):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"content": [{"text": "Claude via router"}]}
        mock_retry.return_value = mock_resp
        llm_router.LLM_PROVIDER = "anthropic"
        result = llm_router.generate("test prompt")
        assert result == "Claude via router"
        llm_router.LLM_PROVIDER = "ollama"

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False)
    @patch("scripts.llm_router._retry_request")
    def test_generate_anthropic_fallback(self, mock_retry):
        mock_resp = MagicMock()
        mock_resp.iter_lines.return_value = [json.dumps({"response": "Ollama"}).encode()]
        mock_retry.return_value = mock_resp
        llm_router.LLM_PROVIDER = "anthropic"
        result = llm_router.generate("test prompt", stream=True)
        assert result == "Ollama"
        llm_router.LLM_PROVIDER = "ollama"

    @patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}, clear=False)
    @patch("scripts.llm_router._retry_request")
    def test_generate_gemini(self, mock_retry):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"candidates": [{"content": {"parts": [{"text": "Gemini via router"}]}}]}
        mock_retry.return_value = mock_resp
        llm_router.LLM_PROVIDER = "gemini"
        result = llm_router.generate("test prompt", stream=False)
        assert result == "Gemini via router"
        llm_router.LLM_PROVIDER = "ollama"

    @patch.dict(os.environ, {"GOOGLE_API_KEY": ""}, clear=False)
    @patch("scripts.llm_router._retry_request")
    def test_generate_gemini_fallback(self, mock_retry):
        mock_resp = MagicMock()
        mock_resp.iter_lines.return_value = [json.dumps({"response": "Ollama"}).encode()]
        mock_retry.return_value = mock_resp
        llm_router.LLM_PROVIDER = "gemini"
        result = llm_router.generate("test prompt", stream=True)
        assert result == "Ollama"
        llm_router.LLM_PROVIDER = "ollama"

    @patch("scripts.llm_router._retry_request", side_effect=Exception("Network down"))
    def test_generate_exception(self, mock_retry):
        llm_router.LLM_PROVIDER = "ollama"
        result = llm_router.generate("test prompt")
        assert result == ""


class TestGetProviderInfo:
    def test_ollama_info(self):
        llm_router.LLM_PROVIDER = "ollama"
        info = llm_router.get_provider_info()
        assert "Ollama" in info

    def test_openai_info(self):
        llm_router.LLM_PROVIDER = "openai"
        info = llm_router.get_provider_info()
        assert "OpenAI" in info

    def test_anthropic_info(self):
        llm_router.LLM_PROVIDER = "anthropic"
        info = llm_router.get_provider_info()
        assert "Anthropic" in info

    def test_gemini_info(self):
        llm_router.LLM_PROVIDER = "gemini"
        info = llm_router.get_provider_info()
        assert "Gemini" in info

    def test_unknown_info(self):
        llm_router.LLM_PROVIDER = "unknown"
        info = llm_router.get_provider_info()
        assert "Ollama" in info
        llm_router.LLM_PROVIDER = "ollama"
