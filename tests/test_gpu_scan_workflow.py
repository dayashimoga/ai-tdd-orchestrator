import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Logic to test (extracted from the workflow's check_gpu.py)
def check_gpu_logic():
    # Check for Cloud Providers first
    provider = os.getenv("LLM_PROVIDER", "auto").lower()
    cloud_configs = [
        ("groq", "GROQ_API_KEY"),
        ("cerebras", "CEREBRAS_API_KEY"),
        ("openai", "OPENAI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("gemini", "GOOGLE_API_KEY"),
    ]
    has_cloud = False
    if provider == "auto":
        for name, key in cloud_configs:
            if os.getenv(key):
                # print(f"✅ Found cloud provider ({name}) via auto failover.")
                has_cloud = True
                break
    else:
        for name, key in cloud_configs:
            if provider == name and os.getenv(key):
                # print(f"✅ Found explicit cloud provider: {name}")
                has_cloud = True
                break
                
    if has_cloud:
        return True # Success (sys.exit(0))

    # Fallback to checking remote Ollama GPU
    # Mocking the import since we're testing the logic block
    try:
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
        from scripts import gpu_platform
        platform, url = gpu_platform.select_platform()
        if platform != "local":
            return True # Success (sys.exit(0))
    except Exception:
        pass
        
    return False # Failure (sys.exit(1))

class TestWorkflowGPUCheck(unittest.TestCase):
    def test_auto_cloud_provider_groq(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "auto", "GROQ_API_KEY": "test-key"}):
            self.assertTrue(check_gpu_logic())

    def test_auto_cloud_provider_gemini(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "auto", "GOOGLE_API_KEY": "test-key"}):
            self.assertTrue(check_gpu_logic())

    def test_explicit_cloud_provider_openai(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "test-key"}):
            self.assertTrue(check_gpu_logic())

    def test_explicit_cloud_provider_mismatch(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "anthropic", "OPENAI_API_KEY": "test-key"}):
            self.assertFalse(check_gpu_logic())

    @patch('scripts.gpu_platform.select_platform', return_value=("colab", "http://colab.url"))
    def test_remote_ollama_colab(self, mock_select):
        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}, clear=True):
            self.assertTrue(check_gpu_logic())

    @patch('scripts.gpu_platform.select_platform', return_value=("local", "http://localhost:11434"))
    def test_fallback_local_failure(self, mock_select):
        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}, clear=True):
            self.assertFalse(check_gpu_logic())

if __name__ == "__main__":
    unittest.main()
