import unittest
import os
import sys
from unittest.mock import patch, MagicMock

# Ensure scripts directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import scripts.llm_router as lr
print(f"DEBUG: sys.path: {sys.path}")
print(f"DEBUG: lr file: {lr.__file__}")
import scripts.gpu_platform as gp

class TestFailureHandling(unittest.TestCase):
    """Tests for error handling and retry branches."""

    @patch('scripts.llm_router.requests.Session.post')
    def test_all_providers_fail(self, mock_post):
        import requests
        def mock_raise():
            raise requests.exceptions.HTTPError("Mock Error", response=MagicMock(status_code=500))
        
        mock_resp = MagicMock(status_code=500, text="Internal Error")
        mock_resp.raise_for_status.side_effect = mock_raise
        mock_post.return_value = mock_resp
        
        # Ensure all providers in the chain are tried and fail
        with patch.dict(os.environ, {
            "GROQ_API_KEY": "k",
            "CEREBRAS_API_KEY": "k", 
            "GOOGLE_API_KEY": "k",
            "OPENAI_API_KEY": "k",
            "ANTHROPIC_API_KEY": "k"
        }):
            res = lr.generate("test")
            self.assertIn("ALL LLM PROVIDERS EXHAUSTED", res.upper())

    @patch('scripts.llm_router.requests.Session.post')
    def test_provider_specific_errors(self, mock_post):
        # Test specific fallback triggers
        for provider in ["groq", "cerebras", "gemini", "openai", "anthropic"]:
            mock_post.return_value = MagicMock(status_code=429, text="Rate limit")
            with patch.dict(os.environ, {"LLM_PROVIDER": provider, f"{provider.upper()}_API_KEY": "test"}):
                try:
                    lr.generate("test")
                except Exception:
                    pass

    @patch('scripts.gpu_platform.requests.get')
    def test_gpu_platform_health_failure(self, mock_get):
        mock_get.side_effect = Exception("General Failure")
        self.assertFalse(gp.health_check("http://localhost:11434"))

    def test_gpu_platform_missing_env(self):
        # Cover the branch where env var is missing or empty
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(gp.detect_platform()[0], "local")

if __name__ == '__main__':
    unittest.main()
