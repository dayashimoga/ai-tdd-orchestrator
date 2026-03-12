import os
import sys
import unittest
import json
from unittest.mock import patch, MagicMock
import requests

# Add repo root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import scripts.gpu_platform as gpu_platform
import scripts.gpu_scheduler as gpu_scheduler

class TestGPUCompute(unittest.TestCase):

    @patch('requests.get')
    def test_health_check(self, mock_get):
        mock_get.return_value.status_code = 200
        self.assertTrue(gpu_platform.health_check("http://gpu/api/generate"))
        
        mock_get.side_effect = Exception("Down")
        self.assertFalse(gpu_platform.health_check("http://gpu/api/generate"))

    def test_resolve_url(self):
        self.assertEqual(gpu_platform._resolve_url("http://host"), "http://host/api/generate")
        self.assertEqual(gpu_platform._resolve_url("http://host/"), "http://host/api/generate")
        self.assertEqual(gpu_platform._resolve_url("http://host/api/generate"), "http://host/api/generate")

    @patch('scripts.gpu_platform.health_check')
    def test_detect_platform_with_env(self, mock_health):
        mock_health.return_value = True
        with patch.dict(os.environ, {"COLAB_OLLAMA_URL": "http://colab"}):
            p, url = gpu_platform.detect_platform()
            self.assertEqual(p, "colab")
            self.assertIn("colab", url)

    @patch('requests.get')
    def test_gpu_scheduler_get_all_status(self, mock_get):
        mock_get.return_value.status_code = 200
        with patch.dict(os.environ, {"COLAB_OLLAMA_URL": "http://colab"}):
            statuses = gpu_scheduler.get_all_platform_status()
            colab_status = next(s for s in statuses if s['platform'] == 'colab')
            self.assertTrue(colab_status['configured'])
            self.assertTrue(colab_status['alive'])

    @patch('scripts.gpu_scheduler.check_platform_health')
    def test_select_best_platform(self, mock_health):
        # Mock colab as down, kaggle as alive
        mock_health.side_effect = lambda k: (True if k == 'kaggle' else False, "http://kaggle" if k == 'kaggle' else "")
        
        p, url = gpu_scheduler.select_best_platform()
        self.assertEqual(p, "kaggle")
        self.assertEqual(url, "http://kaggle")

    @patch('subprocess.run')
    def test_provision_oracle_fail(self, mock_run):
        mock_run.return_value.returncode = 1
        with patch('os.path.exists', return_value=True):
            res = gpu_scheduler.provision_oracle()
            self.assertIsNone(res)

if __name__ == "__main__":
    unittest.main()
