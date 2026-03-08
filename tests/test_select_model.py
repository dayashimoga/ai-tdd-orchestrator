import sys
import os
import unittest
import platform
from unittest.mock import patch, mock_open, MagicMock

# Add project root to path so we can import from scripts
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import scripts.select_model as select_model

class TestSelectModel(unittest.TestCase):
    @patch('builtins.open', new_callable=mock_open, read_data="MemTotal:       16384000 kB\n")
    def test_get_total_memory_gb_linux(self, mock_file):
        # 16384000 kB / 1024 / 1024 = ~15.62 GB
        self.assertAlmostEqual(select_model.get_total_memory_gb(), 15.625)

    @patch('builtins.open', side_effect=Exception("No /proc/meminfo"))
    @patch('subprocess.check_output', return_value=b'17179869184\n')
    def test_get_total_memory_gb_mac(self, mock_sub, mock_file):
        # 17179869184 bytes / 1024 / 1024 / 1024 = 16.0 GB
        self.assertEqual(select_model.get_total_memory_gb(), 16.0)

    @patch('builtins.open', side_effect=Exception("No /proc/meminfo"))
    @patch('subprocess.check_output', side_effect=Exception("No sysctl"))
    @patch('platform.system', return_value="Linux")
    def test_get_total_memory_gb_fallback(self, mock_platform, mock_sub, mock_file):
        # Fallback is 6.0
        self.assertEqual(select_model.get_total_memory_gb(), 6.0)

    @patch('builtins.open', side_effect=Exception("No /proc/meminfo"))
    @patch('subprocess.check_output')
    @patch('platform.system', return_value="Windows")
    def test_get_total_memory_gb_windows(self, mock_platform, mock_sub, mock_file):
        """E4: Test Windows RAM detection via wmic."""
        # First call: sysctl fails, second call: wmic succeeds
        mock_sub.side_effect = [
            Exception("No sysctl"),
            b'\r\nTotalPhysicalMemory=17179869184\r\n'
        ]
        result = select_model.get_total_memory_gb()
        self.assertAlmostEqual(result, 16.0)

    @patch('builtins.open', side_effect=Exception("No /proc/meminfo"))
    @patch('subprocess.check_output', side_effect=Exception("All fail"))
    @patch('platform.system', return_value="Windows")
    def test_get_total_memory_gb_windows_fallback(self, mock_platform, mock_sub, mock_file):
        """E4: Test Windows fallback when wmic also fails."""
        self.assertEqual(select_model.get_total_memory_gb(), 6.0)

    @patch('subprocess.check_output', return_value=b'8192\n8192\n')
    def test_get_gpu_vram_gb_success(self, mock_sub):
        # Two 8GB GPUs = 16.0 GB
        self.assertEqual(select_model.get_gpu_vram_gb(), 16.0)

    @patch('subprocess.check_output', side_effect=Exception("No nvidia-smi"))
    def test_get_gpu_vram_gb_failure(self, mock_sub):
        self.assertEqual(select_model.get_gpu_vram_gb(), 0.0)

    @patch('scripts.select_model.get_total_memory_gb', return_value=32.0)
    @patch('scripts.select_model.get_gpu_vram_gb', return_value=2.0)
    def test_select_optimal_model_high_ram(self, mock_gpu, mock_ram):
        self.assertEqual(select_model.select_optimal_model(), "qwen2.5-coder:7b")

    @patch('scripts.select_model.get_total_memory_gb', return_value=16.0)
    @patch('scripts.select_model.get_gpu_vram_gb', return_value=0.0)
    def test_select_optimal_model_mid_ram(self, mock_gpu, mock_ram):
        self.assertEqual(select_model.select_optimal_model(), "qwen2.5-coder:7b")

    @patch('scripts.select_model.get_total_memory_gb', return_value=7.0)
    @patch('scripts.select_model.get_gpu_vram_gb', return_value=0.0)
    def test_select_optimal_model_low_ram(self, mock_gpu, mock_ram):
        self.assertEqual(select_model.select_optimal_model(), "qwen2.5-coder:3b")

    @patch('scripts.select_model.get_total_memory_gb', return_value=4.0)
    @patch('scripts.select_model.get_gpu_vram_gb', return_value=0.0)
    def test_select_optimal_model_fallback(self, mock_gpu, mock_ram):
        self.assertEqual(select_model.select_optimal_model(), "qwen2.5-coder:3b")

    @patch('scripts.select_model.get_total_memory_gb', return_value=32.0)
    @patch('scripts.select_model.get_gpu_vram_gb', return_value=24.0)
    def test_select_optimal_model_high_vram(self, mock_gpu, mock_ram):
        self.assertEqual(select_model.select_optimal_model(), "qwen2.5-coder:32b")

    @patch('scripts.select_model.get_total_memory_gb', return_value=16.0)
    @patch('scripts.select_model.get_gpu_vram_gb', return_value=0.0)
    @patch('os.getenv', side_effect=lambda k, d=None: "dummy_file" if k in ["GITHUB_ENV", "GITHUB_STEP_SUMMARY"] else d)
    @patch('builtins.print')
    @patch('builtins.open', new_callable=mock_open)
    def test_main_execution(self, mock_file, mock_print, mock_getenv, mock_vram, mock_ram):
        # Run the script as main to cover all telemetry logic
        select_model.main()
        self.assertTrue(mock_print.called)
        self.assertTrue(mock_file.called)

if __name__ == '__main__':
    unittest.main()
