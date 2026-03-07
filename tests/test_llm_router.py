"""Tests for scripts/llm_router.py"""
import os
import json
from unittest.mock import patch, MagicMock
import pytest
from scripts.llm_router import (
    _ollama_generate, _openai_generate, _anthropic_generate,
    _gemini_generate, generate, get_provider_info,
)


class TestOllamaGenerate:
    @patch("scripts.llm_router.requests.post")
    def test_ollama_stream(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = [
            json.dumps({"response": "Hello "}).encode(),
            json.dumps({"response": "World"}).encode(),
        ]
        mock_post.return_value = mock_resp
        result = _ollama_generate("test", "qwen", "http://localhost/api/generate", 0.2, 8192, True)
        assert result == "Hello World"

    @patch("scripts.llm_router.requests.post")
    def test_ollama_no_stream(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"response": "Generated code"}
        mock_post.return_value = mock_resp
        result = _ollama_generate("test", "qwen", "http://localhost/api/generate", 0.2, 8192, False)
        assert result == "Generated code"


class TestOpenAIGenerate:
    @patch("scripts.llm_router.requests.post")
    def test_openai_no_stream(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "OpenAI response"}}]
        }
        mock_post.return_value = mock_resp
        result = _openai_generate("test", "gpt-4o-mini", "key123", 0.2, False)
        assert result == "OpenAI response"


class TestAnthropicGenerate:
    @patch("scripts.llm_router.requests.post")
    def test_anthropic(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "content": [{"type": "text", "text": "Claude response"}]
        }
        mock_post.return_value = mock_resp
        result = _anthropic_generate("test", "claude-3-haiku", "key123", 0.2)
        assert result == "Claude response"


class TestGeminiGenerate:
    @patch("scripts.llm_router.requests.post")
    def test_gemini(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Gemini response"}]}}]
        }
        mock_post.return_value = mock_resp
        result = _gemini_generate("test", "gemini-1.5-flash", "key123", 0.2)
        assert result == "Gemini response"


class TestGenerate:
    @patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}, clear=False)
    @patch("scripts.llm_router.requests.post")
    def test_generate_ollama_default(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_lines.return_value = [json.dumps({"response": "OK"}).encode()]
        mock_post.return_value = mock_resp
        # Need to reimport to pick up env var
        from scripts import llm_router
        llm_router.LLM_PROVIDER = "ollama"
        result = llm_router.generate("test prompt", stream=True)
        assert result == "OK"

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "gpt-4o"}, clear=False)
    @patch("scripts.llm_router.requests.post")
    def test_generate_openai(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "OpenAI via router"}}]
        }
        mock_post.return_value = mock_resp
        from scripts import llm_router
        llm_router.LLM_PROVIDER = "openai"
        result = llm_router.generate("test prompt", stream=False)
        assert result == "OpenAI via router"
        llm_router.LLM_PROVIDER = "ollama"  # reset


class TestGetProviderInfo:
    def test_ollama_info(self):
        from scripts import llm_router
        llm_router.LLM_PROVIDER = "ollama"
        info = llm_router.get_provider_info()
        assert "Ollama" in info

    def test_openai_info(self):
        from scripts import llm_router
        llm_router.LLM_PROVIDER = "openai"
        info = llm_router.get_provider_info()
        assert "OpenAI" in info
        llm_router.LLM_PROVIDER = "ollama"
