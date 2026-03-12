import unittest
import os
import sys
import json
import requests
from unittest.mock import MagicMock, patch, mock_open

# Ensure scripts directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import scripts.llm_router as llm_router

class TestLLMRouter(unittest.TestCase):
    def setUp(self):
        # Clear environment variables before each test
        self.env_patcher = patch.dict(os.environ, {}, clear=True)
        self.env_patcher.start()
        # Reset provider info
        if hasattr(llm_router, '_session'):
            llm_router._session = None

    def tearDown(self):
        self.env_patcher.stop()

    @patch('requests.Session.post')
    def test_ollama_generate_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "ollama response", "done": True}
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama", "OLLAMA_URL": "http://test:11434/api/generate"}):
            result = llm_router.generate("test prompt", stream=False)
            self.assertEqual(result, "ollama response")

    @patch('requests.Session.post')
    def test_openai_generate_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "openai response"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}
        }
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "test_key"}):
            result = llm_router.generate("test prompt", stream=False)
            self.assertEqual(result, "openai response")

    @patch('requests.Session.post')
    def test_anthropic_generate_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [{"text": "anthropic response"}],
            "usage": {"input_tokens": 10, "output_tokens": 5}
        }
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {"LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "test_key"}):
            result = llm_router.generate("test prompt", stream=False)
            self.assertEqual(result, "anthropic response")

    @patch('requests.Session.post')
    def test_gemini_generate_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "gemini response"}]}}]
        }
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {"LLM_PROVIDER": "gemini", "GOOGLE_API_KEY": "test_key"}):
            result = llm_router.generate("test prompt", stream=False)
            self.assertEqual(result, "gemini response")

    @patch('requests.Session.post')
    def test_groq_generate_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "groq response"}}]
        }
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {"LLM_PROVIDER": "groq", "GROQ_API_KEY": "test_key"}):
            result = llm_router.generate("test prompt", stream=False)
            self.assertEqual(result, "groq response")

    @patch('requests.Session.post')
    def test_cerebras_generate_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "cerebras response"}}]
        }
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {"LLM_PROVIDER": "cerebras", "CEREBRAS_API_KEY": "test_key"}):
            result = llm_router.generate("test prompt", stream=False)
            self.assertEqual(result, "cerebras response")

    @patch('requests.Session.post')
    def test_provider_failover_logic(self, mock_post):
        # Groq (429) -> 1 response
        # Cerebras (500) -> 3 retries (default MAX_RETRIES=3) -> 3 responses
        # Gemini (200) -> 1 response
        
        mock_resp_fail_429 = MagicMock()
        mock_resp_fail_429.status_code = 429
        mock_resp_fail_429.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_resp_fail_429)

        mock_resp_fail_500 = MagicMock()
        mock_resp_fail_500.status_code = 500
        mock_resp_fail_500.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_resp_fail_500)

        mock_resp_success = MagicMock()
        mock_resp_success.status_code = 200
        mock_resp_success.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "gemini win"}]}}]
        }

        # Sequence: Groq(429), Cerebras(500), Cerebras(500), Cerebras(500), Gemini(200)
        mock_post.side_effect = [
            mock_resp_fail_429,
            mock_resp_fail_500,
            mock_resp_fail_500,
            mock_resp_fail_500,
            mock_resp_success
        ]

        with patch.dict(os.environ, {
            "LLM_PROVIDER": "auto",
            "GROQ_API_KEY": "gkey",
            "CEREBRAS_API_KEY": "ckey",
            "GOOGLE_API_KEY": "gmkey"
        }):
            # Reduce backoff for speed in tests
            with patch('scripts.llm_router.BACKOFF_BASE', 0.01):
                result = llm_router.generate("prompt", stream=False)
                # The chain is [groq, cerebras, gemini, ...]
                # mock_post.side_effect is [429 (groq), 500 (cerebras)x3, 200 (gemini)] -> gemini wins
                self.assertEqual(result, "gemini win")

    def test_get_provider_info(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "openai", "OPENAI_MODEL": "gpt-custom"}):
            self.assertIn("OpenAI (gpt-custom)", llm_router.get_provider_info())
        
        with patch.dict(os.environ, {"LLM_PROVIDER": "anthropic", "ANTHROPIC_MODEL": "claude-custom"}):
            self.assertIn("Anthropic (claude-custom)", llm_router.get_provider_info())

        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama", "OLLAMA_MODEL": "ollama-custom"}):
            self.assertIn("Ollama (ollama-custom)", llm_router.get_provider_info())

    @patch('requests.Session.post')
    def test_generate_streaming_ollama(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = [
            json.dumps({"response": "Hello", "done": False}).encode(),
            json.dumps({"response": " world", "done": True}).encode(),
        ]
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama", "OLLAMA_URL": "http://test:11434/api/generate"}):
            result = llm_router.generate("test prompt", stream=True)
            self.assertEqual(result, "Hello world")

    @patch('requests.Session.post')
    def test_generate_streaming_openai(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = [
            b"data: " + json.dumps({"choices": [{"delta": {"content": "Open"}}]}).encode(),
            b"data: " + json.dumps({"choices": [{"delta": {"content": "AI"}}]}).encode(),
            b"data: [DONE]"
        ]
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "test_key"}):
            result = llm_router.generate("test prompt", stream=True)
            self.assertEqual(result, "OpenAI")

    @patch('requests.Session.get')
    def test_retry_request_get(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        res = llm_router._retry_request("GET", "http://test")
        self.assertEqual(res, mock_response)

    @patch('requests.Session.post')
    def test_retry_request_exhaustion(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError("timeout")
        with patch('scripts.llm_router.BACKOFF_BASE', 0.001):
            with self.assertRaises(requests.exceptions.ConnectionError):
                llm_router._retry_request("POST", "http://test", max_retries=2)

    @patch('requests.Session.post')
    def test_stream_usage_and_json_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = [
            b"invalid json",
            b"data: " + json.dumps({"choices": [{"delta": {"content": "text"}}], "usage": {"prompt_tokens": 5}}).encode(),
            b"data: [DONE]"
        ]
        mock_post.return_value = mock_response
        with patch.dict(os.environ, {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "test"}):
            result = llm_router.generate("test", stream=True)
            self.assertEqual(result, "text")

    @patch('requests.Session.post')
    def test_ollama_stream_usage(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = [
            json.dumps({"response": "Hi", "done": False}).encode(),
            json.dumps({"response": "", "done": True, "prompt_eval_count": 10, "eval_count": 5}).encode(),
        ]
        mock_post.return_value = mock_response
        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama", "OLLAMA_URL": "http://test"}):
            result = llm_router.generate("test", stream=True)
            self.assertEqual(result, "Hi")
        # HTTP 429
        err_429 = requests.exceptions.HTTPError()
        err_429.response = MagicMock(status_code=429)
        self.assertTrue(llm_router._is_failover_error(err_429))

        # HTTP 500
        err_500 = requests.exceptions.HTTPError()
        err_500.response = MagicMock(status_code=500)
        self.assertTrue(llm_router._is_failover_error(err_500))

        # Connection error
        self.assertTrue(llm_router._is_failover_error(requests.exceptions.ConnectionError()))

        # String matching
        self.assertTrue(llm_router._is_failover_error(Exception("Rate limit reached")))

    @patch('requests.Session.post')
    def test_generate_all_providers_fail(self, mock_post):
        mock_resp_fail = MagicMock()
        mock_resp_fail.status_code = 429
        mock_resp_fail.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_resp_fail)
        mock_post.side_effect = [mock_resp_fail] * 10 

        with patch.dict(os.environ, {"LLM_PROVIDER": "auto", "GROQ_API_KEY": "k", "CEREBRAS_API_KEY": "k", "GOOGLE_API_KEY": "k", "OPENAI_API_KEY": "k", "ANTHROPIC_API_KEY": "k"}):
            result = llm_router.generate("test", stream=False)
            self.assertEqual(result, "")

    @patch('requests.Session.post')
    def test_generate_streaming_gemini(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = [
            b"data: " + json.dumps({"candidates": [{"content": {"parts": [{"text": "Gemini"}]}}]}).encode(),
            b"data: " + json.dumps({"candidates": [{"content": {"parts": [{"text": " Stream"}]}}], "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5, "totalTokenCount": 15}}).encode(),
        ]
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {"LLM_PROVIDER": "gemini", "GOOGLE_API_KEY": "test_key"}):
            result = llm_router.generate("test prompt", stream=True)
            self.assertEqual(result, "Gemini Stream")

    @patch('requests.Session.post')
    def test_gemini_generate_non_stream_usage(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "gemini res"}]}}],
            "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3}
        }
        mock_post.return_value = mock_response
        with patch.dict(os.environ, {"LLM_PROVIDER": "gemini", "GOOGLE_API_KEY": "test_key"}):
            result = llm_router.generate("test prompt", stream=False)
            self.assertEqual(result, "gemini res")

    @patch('requests.Session.post')
    def test_gemini_generate_empty_candidates(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"candidates": []}
        mock_post.return_value = mock_response
        with patch.dict(os.environ, {"LLM_PROVIDER": "gemini", "GOOGLE_API_KEY": "test_key"}):
            result = llm_router.generate("test prompt", stream=False)
            self.assertEqual(result, "")

    @patch('scripts.gpu_platform.select_platform')
    def test_ollama_generate_url_from_platform(self, mock_select):
        mock_select.return_value = ("vastai", "http://vast:11434/api/generate")
        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama", "OLLAMA_URL": ""}):
            with patch('requests.Session.post') as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"response": "res", "done": True}
                mock_post.return_value = mock_response
                result = llm_router.generate("test", stream=False)
                self.assertEqual(result, "res")

    @patch('requests.Session.post')
    def test_generate_connection_failover_all(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError("offline")
        with patch.dict(os.environ, {"LLM_PROVIDER": "auto", "GROQ_API_KEY": "k", "OPENAI_API_KEY": "k"}):
            result = llm_router.generate("test", stream=False)
            self.assertEqual(result, "")

    @patch('requests.Session.post')
    def test_generate_generic_exception_failover(self, mock_post):
        # mock_post side effect for chain [groq, cerebras, gemini, ollama, openai, ...]
        # [Exception (groq), success (cerebras)] -> cerebras wins
        mock_post.side_effect = [
            Exception("Rate limit 429"), 
            MagicMock(status_code=200, json=lambda: {"choices": [{"message": {"content": "win"}}]})
        ]
        with patch.dict(os.environ, {"LLM_PROVIDER": "auto", "GROQ_API_KEY": "k", "CEREBRAS_API_KEY": "k"}):
            result = llm_router.generate("test", stream=False)
            self.assertEqual(result, "win")

if __name__ == '__main__':
    unittest.main()
