"""Unit tests for gpu_platform.py with failover."""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import scripts.gpu_platform as gpu_platform


class TestPlatformRegistry(unittest.TestCase):
    """Tests for platform registry."""

    def test_all_platforms_exist(self):
        for key in ["local", "colab", "kaggle", "vastai", "runpod",
                     "lightning", "huggingface", "oracle", "sagemaker",
                     "paperspace", "custom"]:
            self.assertIn(key, gpu_platform.PLATFORMS)

    def test_failover_order(self):
        self.assertEqual(gpu_platform.FAILOVER_ORDER[0], "colab")
        self.assertIn("kaggle", gpu_platform.FAILOVER_ORDER)
        self.assertIn("vastai", gpu_platform.FAILOVER_ORDER)


class TestResolveURL(unittest.TestCase):
    """Tests for URL resolution."""

    def test_appends_api_generate(self):
        self.assertEqual(gpu_platform._resolve_url("https://x.ngrok.io"),
                         "https://x.ngrok.io/api/generate")

    def test_no_double_append(self):
        self.assertEqual(gpu_platform._resolve_url("https://x.ngrok.io/api/generate"),
                         "https://x.ngrok.io/api/generate")

    def test_strips_trailing_slash(self):
        self.assertEqual(gpu_platform._resolve_url("https://x.ngrok.io/"),
                         "https://x.ngrok.io/api/generate")


class TestHealthCheck(unittest.TestCase):
    """Tests for health_check."""

    @patch('requests.get')
    def test_healthy(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200)
        self.assertTrue(gpu_platform.health_check("http://localhost:11434/api/generate"))

    @patch('requests.get')
    def test_unhealthy(self, mock_get):
        mock_get.return_value = MagicMock(status_code=500)
        self.assertFalse(gpu_platform.health_check("http://localhost:11434/api/generate"))

    @patch('requests.get', side_effect=Exception("Connection refused"))
    def test_unreachable(self, mock_get):
        self.assertFalse(gpu_platform.health_check("http://dead:11434/api/generate"))


class TestDetectPlatform(unittest.TestCase):
    """Tests for detect_platform (no health check)."""

    def test_default_local(self):
        with patch.dict(os.environ, {}, clear=True):
            platform, url = gpu_platform.detect_platform()
            self.assertEqual(platform, "local")
            self.assertIn("localhost", url)

    def test_explicit_url(self):
        with patch.dict(os.environ, {"OLLAMA_URL": "https://my-gpu.com/api/generate"}):
            platform, url = gpu_platform.detect_platform()
            self.assertEqual(platform, "custom")

    def test_colab_detected(self):
        with patch.dict(os.environ, {"COLAB_OLLAMA_URL": "https://abc.ngrok.io"}, clear=True):
            platform, url = gpu_platform.detect_platform()
            self.assertEqual(platform, "colab")

    def test_kaggle_detected(self):
        with patch.dict(os.environ, {"KAGGLE_OLLAMA_URL": "https://k.ngrok.io"}, clear=True):
            platform, url = gpu_platform.detect_platform()
            self.assertEqual(platform, "kaggle")


class TestDetectWithFailover(unittest.TestCase):
    """Tests for detect_with_failover (with health checks)."""

    @patch('scripts.gpu_platform.health_check', return_value=True)
    def test_primary_healthy(self, mock_hc):
        with patch.dict(os.environ, {"COLAB_OLLAMA_URL": "https://abc.ngrok.io"}, clear=True):
            platform, url = gpu_platform.detect_with_failover()
            self.assertEqual(platform, "colab")

    @patch('scripts.gpu_platform.health_check', side_effect=[False, True])
    def test_failover_to_second(self, mock_hc):
        with patch.dict(os.environ, {
            "COLAB_OLLAMA_URL": "https://dead.ngrok.io",
            "KAGGLE_OLLAMA_URL": "https://alive.ngrok.io",
        }, clear=True):
            platform, url = gpu_platform.detect_with_failover()
            self.assertEqual(platform, "kaggle")

    @patch('scripts.gpu_platform.health_check', return_value=False)
    def test_all_down_fallback_local(self, mock_hc):
        with patch.dict(os.environ, {
            "COLAB_OLLAMA_URL": "https://dead1.ngrok.io",
            "KAGGLE_OLLAMA_URL": "https://dead2.ngrok.io",
        }, clear=True):
            platform, url = gpu_platform.detect_with_failover()
            self.assertEqual(platform, "local")
            self.assertIn("localhost", url)

    def test_no_platforms_configured(self):
        with patch.dict(os.environ, {}, clear=True):
            platform, url = gpu_platform.detect_with_failover()
            self.assertEqual(platform, "local")

    def test_explicit_url_skips_failover(self):
        with patch.dict(os.environ, {"OLLAMA_URL": "https://manual.com/api/generate"}, clear=True):
            platform, url = gpu_platform.detect_with_failover()
            self.assertEqual(platform, "custom")


class TestSelectPlatform(unittest.TestCase):
    """Tests for select_platform."""

    def test_auto_mode(self):
        with patch.dict(os.environ, {"GPU_PLATFORM": "auto"}, clear=True):
            platform, url = gpu_platform.select_platform(use_failover=False)
            self.assertEqual(platform, "local")

    def test_manual_override(self):
        with patch.dict(os.environ, {"GPU_PLATFORM": "colab", "COLAB_OLLAMA_URL": "https://x.io"}):
            platform, url = gpu_platform.select_platform(use_failover=False)
            self.assertEqual(platform, "colab")

    @patch('scripts.gpu_platform.detect_with_failover', return_value=("kaggle", "https://k.io/api/generate"))
    def test_with_failover(self, mock_detect):
        with patch.dict(os.environ, {"GPU_PLATFORM": "auto"}, clear=True):
            platform, url = gpu_platform.select_platform(use_failover=True)
            self.assertEqual(platform, "kaggle")


class TestHelpers(unittest.TestCase):
    """Tests for get_platform_info and list_platforms."""

    def test_get_info(self):
        info = gpu_platform.get_platform_info("colab")
        self.assertEqual(info["gpu"], "NVIDIA T4 (15GB)")

    def test_get_info_unknown(self):
        info = gpu_platform.get_platform_info("nonexistent")
        self.assertEqual(info["name"], "Local Ollama")

    def test_list_platforms(self):
        output = gpu_platform.list_platforms()
        self.assertIn("Google Colab", output)
        self.assertIn("Kaggle", output)
        self.assertIn("FREE", output)

class TestCoverageGap(unittest.TestCase):
    """Tests to fill coverage gaps in gpu_platform.py."""

    @patch('requests.get', side_effect=Exception("Failed"))
    def test_health_check_exception(self, mock_get):
        self.assertFalse(gpu_platform.health_check("http://bad-url"))

    def test_detect_platform_with_env(self):
        with patch.dict(os.environ, {"COLAB_OLLAMA_URL": "http://colab"}):
            p, url = gpu_platform.detect_platform()
            self.assertEqual(p, "colab")
            self.assertEqual(url, "http://colab/api/generate")

    @patch('scripts.gpu_platform.health_check', return_value=True)
    def test_detect_with_failover_parallel(self, mock_hc):
        with patch.dict(os.environ, {"COLAB_OLLAMA_URL": "http://colab", "KAGGLE_OLLAMA_URL": "http://kaggle"}):
            p, url = gpu_platform.detect_with_failover()
            self.assertIn(p, ["colab", "kaggle"]) # Parallel choice

    @patch('scripts.gpu_platform.health_check', return_value=False)
    def test_detect_with_failover_all_down(self, mock_hc):
        with patch.dict(os.environ, {"COLAB_OLLAMA_URL": "http://colab"}):
            p, url = gpu_platform.detect_with_failover()
            self.assertEqual(p, "local")

    def test_select_platform_manual(self):
        with patch.dict(os.environ, {"GPU_PLATFORM": "colab", "COLAB_OLLAMA_URL": "http://colab"}):
            p, url = gpu_platform.select_platform()
            self.assertEqual(p, "colab")
            self.assertEqual(url, "http://colab")


if __name__ == '__main__':
    unittest.main()
