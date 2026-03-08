"""Tests for scripts/gpu_scheduler.py"""
import os
import json
import subprocess
from unittest.mock import patch, MagicMock
import pytest

from scripts import gpu_scheduler

class TestGPUScheduler:

    @patch("scripts.gpu_scheduler.health_check")
    @patch.dict(os.environ, {"COLAB_OLLAMA_URL": "http://colab.ngrok"}, clear=True)
    def test_check_platform_health_configured_and_alive(self, mock_health):
        mock_health.return_value = True
        alive, url = gpu_scheduler.check_platform_health("colab")
        assert alive is True
        assert url == "http://colab.ngrok/api/generate"
        mock_health.assert_called_once_with("http://colab.ngrok/api/generate")

    @patch("scripts.gpu_scheduler.health_check")
    @patch.dict(os.environ, {"COLAB_OLLAMA_URL": "http://colab.ngrok"}, clear=True)
    def test_check_platform_health_configured_not_alive(self, mock_health):
        mock_health.return_value = False
        alive, url = gpu_scheduler.check_platform_health("colab")
        assert alive is False
        assert url == ""

    @patch.dict(os.environ, {}, clear=True)
    def test_check_platform_health_not_configured(self):
        alive, url = gpu_scheduler.check_platform_health("colab")
        assert alive is False
        assert url == ""

    @patch("scripts.gpu_scheduler.health_check")
    def test_check_platform_health_local(self, mock_health):
        mock_health.return_value = True
        alive, url = gpu_scheduler.check_platform_health("local")
        assert alive is True
        assert url == "http://localhost:11434/api/generate"

    def test_check_platform_health_unknown(self):
        alive, url = gpu_scheduler.check_platform_health("unknown")
        assert alive is False
        assert url == ""

    @patch("scripts.gpu_scheduler.check_platform_health")
    def test_get_all_platform_status(self, mock_check):
        mock_check.side_effect = lambda key: (True, f"http://{key}") if key in ["colab", "local"] else (False, "")
        
        with patch.dict(os.environ, {"COLAB_OLLAMA_URL": "url", "ORACLE_OLLAMA_URL": "url"}):
            statuses = gpu_scheduler.get_all_platform_status()
            
        assert len(statuses) > 0
        
        colab = next(s for s in statuses if s["platform"] == "colab")
        assert colab["configured"] is True
        assert colab["alive"] is True
        
        oracle = next(s for s in statuses if s["platform"] == "oracle")
        assert oracle["configured"] is True
        assert oracle["alive"] is False
        
        kaggle = next(s for s in statuses if s["platform"] == "kaggle")
        assert kaggle["configured"] is False
        assert kaggle["alive"] is False

    def test_print_status_table(self, capsys):
        statuses = [
            {"platform": "colab", "name": "Colab", "configured": True, "alive": True, "url": "http://url", "free": True, "gpu": "T4"},
            {"platform": "oracle", "name": "Oracle", "configured": True, "alive": False, "url": "", "free": True, "gpu": "A10"},
            {"platform": "kaggle", "name": "Kaggle", "configured": False, "alive": False, "url": "", "free": True, "gpu": "T4"}
        ]
        gpu_scheduler.print_status_table(statuses)
        captured = capsys.readouterr()
        assert "LIVE" in captured.out
        assert "DOWN" in captured.out
        assert "N/A" in captured.out

    @patch("scripts.gpu_scheduler.check_platform_health")
    def test_select_best_platform_free(self, mock_check):
        def side_effect(key):
            if key == "colab": return True, "http://colab"
            return False, ""
        mock_check.side_effect = side_effect
        
        platform, url = gpu_scheduler.select_best_platform()
        assert platform == "colab"
        assert url == "http://colab"

    @patch("scripts.gpu_scheduler.check_platform_health")
    def test_select_best_platform_oracle(self, mock_check):
        def side_effect(key):
            if key == "oracle": return True, "http://oracle"
            return False, ""
        mock_check.side_effect = side_effect
        
        platform, url = gpu_scheduler.select_best_platform()
        assert platform == "oracle"
        assert url == "http://oracle"

    @patch("scripts.gpu_scheduler.check_platform_health")
    @patch("scripts.gpu_scheduler.provision_oracle")
    def test_select_best_platform_provision(self, mock_provision, mock_check):
        mock_check.return_value = (False, "")
        mock_provision.return_value = "http://provisioned"
        
        platform, url = gpu_scheduler.select_best_platform(allow_provision=True)
        assert platform == "oracle"
        assert url == "http://provisioned"

    @patch("scripts.gpu_scheduler.check_platform_health")
    def test_select_best_platform_local(self, mock_check):
        def side_effect(key):
            if key == "local": return True, "http://local"
            return False, ""
        mock_check.side_effect = side_effect
        
        platform, url = gpu_scheduler.select_best_platform()
        assert platform == "local"
        assert url == "http://local"

    @patch("scripts.gpu_scheduler.check_platform_health")
    def test_select_best_platform_none(self, mock_check):
        mock_check.return_value = (False, "")
        platform, url = gpu_scheduler.select_best_platform()
        assert platform == "local"
        assert url == "http://localhost:11434/api/generate"

    @patch("os.path.exists")
    def test_provision_oracle_no_tf(self, mock_exists):
        mock_exists.return_value = False
        assert gpu_scheduler.provision_oracle() is None

    @patch("os.path.exists")
    @patch("subprocess.run")
    def test_provision_oracle_budget_fail(self, mock_run, mock_exists):
        def exists_effect(path):
            return True
        mock_exists.side_effect = exists_effect
        
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_run.return_value = mock_res
        
        assert gpu_scheduler.provision_oracle() is None

    @patch("os.path.exists")
    @patch("subprocess.run")
    def test_provision_oracle_init_fail(self, mock_run, mock_exists):
        def exists_effect(path):
            if path.endswith("main.tf"): return True
            return False
        mock_exists.side_effect = exists_effect
        
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_res.stderr = "error"
        mock_run.return_value = mock_res
        
        assert gpu_scheduler.provision_oracle() is None

    @patch("os.path.exists")
    @patch("subprocess.run")
    def test_provision_oracle_apply_fail(self, mock_run, mock_exists):
        mock_exists.side_effect = lambda p: p.endswith("main.tf")
        
        def run_effect(args, **kwargs):
            res = MagicMock()
            if "init" in args:
                res.returncode = 0
            else:
                res.returncode = 1
                res.stderr = "error"
            return res
        mock_run.side_effect = run_effect
        
        assert gpu_scheduler.provision_oracle() is None

    @patch("os.path.exists")
    @patch("subprocess.run")
    @patch("subprocess.Popen")
    @patch("scripts.gpu_scheduler.health_check")
    @patch("time.sleep")
    def test_provision_oracle_success(self, mock_sleep, mock_health, mock_popen, mock_run, mock_exists):
        mock_exists.side_effect = lambda p: True
        mock_health.return_value = True
        
        def run_effect(args, **kwargs):
            res = MagicMock()
            res.returncode = 0
            if "output" in args:
                res.stdout = json.dumps({"ollama_url": {"value": "http://oracle.vm/api/generate"}})
            return res
        mock_run.side_effect = run_effect
        
        url = gpu_scheduler.provision_oracle()
        assert url == "http://oracle.vm/api/generate"

    @patch("os.path.exists")
    @patch("subprocess.run")
    @patch("subprocess.Popen")
    @patch("scripts.gpu_scheduler.health_check")
    @patch("time.sleep")
    def test_provision_oracle_timeout(self, mock_sleep, mock_health, mock_popen, mock_run, mock_exists):
        mock_exists.side_effect = lambda p: True
        mock_health.return_value = False
        
        def run_effect(args, **kwargs):
            res = MagicMock()
            res.returncode = 0
            if "output" in args:
                res.stdout = json.dumps({"ollama_url": {"value": "http://oracle.vm/api/generate"}})
            return res
        mock_run.side_effect = run_effect
        
        url = gpu_scheduler.provision_oracle()
        assert url == "http://oracle.vm/api/generate"

    @patch("os.path.exists")
    @patch("subprocess.run")
    def test_provision_oracle_invalid_json(self, mock_run, mock_exists):
        mock_exists.side_effect = lambda p: p.endswith("main.tf")
        
        def run_effect(args, **kwargs):
            res = MagicMock()
            res.returncode = 0
            if "output" in args:
                res.stdout = "invalid json"
            return res
        mock_run.side_effect = run_effect
        
        assert gpu_scheduler.provision_oracle() is None

    @patch("os.path.exists")
    def test_destroy_oracle_no_tf(self, mock_exists):
        mock_exists.return_value = False
        assert gpu_scheduler.destroy_oracle() is False

    @patch("os.path.exists")
    @patch("subprocess.run")
    def test_destroy_oracle_success(self, mock_run, mock_exists):
        mock_exists.return_value = True
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run.return_value = mock_res
        
        assert gpu_scheduler.destroy_oracle() is True

    @patch("os.path.exists")
    @patch("subprocess.run")
    def test_destroy_oracle_fail(self, mock_run, mock_exists):
        mock_exists.return_value = True
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_res.stderr = "error"
        mock_run.return_value = mock_res
        
        assert gpu_scheduler.destroy_oracle() is False

    @patch("scripts.gpu_scheduler.get_all_platform_status")
    @patch("scripts.gpu_scheduler.print_status_table")
    def test_main_status(self, mock_print, mock_get):
        with patch('sys.argv', ['gpu_scheduler.py', '--status']):
            gpu_scheduler.main()
        mock_get.assert_called_once()
        mock_print.assert_called_once()

    @patch("scripts.gpu_scheduler.destroy_oracle")
    def test_main_destroy(self, mock_destroy):
        with patch('sys.argv', ['gpu_scheduler.py', '--destroy']):
            gpu_scheduler.main()
        mock_destroy.assert_called_once()

    @patch("scripts.gpu_scheduler.select_best_platform")
    def test_main_run(self, mock_select):
        mock_select.return_value = ("colab", "http://colab")
        with patch('sys.argv', ['gpu_scheduler.py']):
            gpu_scheduler.main()
        mock_select.assert_called_with(allow_provision=False)

    @patch("scripts.gpu_scheduler.select_best_platform")
    def test_main_export(self, mock_select, capsys):
        mock_select.return_value = ("colab", "http://colab/api/generate")
        with patch('sys.argv', ['gpu_scheduler.py', '--export']):
            gpu_scheduler.main()
        captured = capsys.readouterr()
        assert "export COLAB_OLLAMA_URL=\"http://colab\"" in captured.out
        assert "export OLLAMA_URL=\"http://colab/api/generate\"" in captured.out
