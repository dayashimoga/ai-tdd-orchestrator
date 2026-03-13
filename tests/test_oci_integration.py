import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Ensure scripts directory is in path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import scripts.gpu_platform as gpu_platform
import scripts.llm_router as llm_router
import scripts.oci_manager as oci_manager

class TestOCIIntegration(unittest.TestCase):

    def setUp(self):
        # Reset env vars
        if "OCI_CREDITS_AVAILABLE" in os.environ:
            del os.environ["OCI_CREDITS_AVAILABLE"]
        if "ORACLE_OLLAMA_URL" in os.environ:
            del os.environ["ORACLE_OLLAMA_URL"]

    def test_oci_credit_detection_manual(self):
        """Test that OCI_CREDITS_AVAILABLE env var works."""
        with patch.dict(os.environ, {"OCI_CREDITS_AVAILABLE": "100.0"}):
            self.assertEqual(oci_manager.check_oci_credits(), 100.0)
        
        with patch.dict(os.environ, {"OCI_CREDITS_AVAILABLE": "true"}):
            self.assertEqual(oci_manager.check_oci_credits(), 400.0)

    @patch('scripts.gpu_platform.health_check')
    @patch('scripts.gpu_platform.check_oci_credits')
    def test_oci_prioritization(self, mock_credits, mock_health):
        """Test that OCI is prioritized when credits are available and it's healthy."""
        mock_credits.return_value = True # True means > 0 credits
        mock_health.return_value = True
        
        with patch.dict(os.environ, {"ORACLE_OLLAMA_URL": "http://oracle-gpu:11434"}):
            platform, url = gpu_platform.detect_with_failover()
            self.assertEqual(platform, "oracle")
            self.assertIn("oracle-gpu", url)

    @patch('scripts.gpu_platform.health_check')
    @patch('scripts.gpu_platform.check_oci_credits')
    def test_oci_skip_when_no_credits(self, mock_credits, mock_health):
        """Test that OCI is NOT prioritized when credits are 0."""
        mock_credits.return_value = False
        mock_health.return_value = True
        
        # Clear other env vars that might interfere
        env_patches = {
            "ORACLE_OLLAMA_URL": "http://oracle-gpu:11434",
            "COLAB_OLLAMA_URL": "http://colab-gpu:11434",
            "KAGGLE_OLLAMA_URL": "",
            "LIGHTHOUSE_OLLAMA_URL": ""
        }
        
        with patch.dict(os.environ, env_patches):
            platform, url = gpu_platform.detect_with_failover()
            # Should pick the first healthy one in standard order (colab is before oracle in FAILOVER_ORDER)
            # Wait, I moved oracle to the TOP of FAILOVER_ORDER.
            # But detect_with_failover should only return it if check_oci_credits() is True.
            self.assertEqual(platform, "colab")

    @patch('scripts.llm_router._has_oci_credits')
    @patch('scripts.gpu_platform.select_platform')
    def test_llm_router_info_with_oci(self, mock_select, mock_has_credits):
        """Test that llm_router shows OCI credit utilization info."""
        mock_has_credits.return_value = True
        mock_select.return_value = ("oracle", "http://oracle-gpu:11434")
        
        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}):
            info = llm_router.get_provider_info()
            self.assertIn("Oracle Cloud", info)
            self.assertIn("[CREDIT UTILIZATION]", info)

if __name__ == "__main__":
    unittest.main()
