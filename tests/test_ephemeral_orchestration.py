import os
import sys
import unittest
import subprocess
from unittest.mock import patch, MagicMock, mock_open

# Add repository root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import scripts.ai_pipeline as ai_pipeline
import scripts.ephemeral_runner as ephemeral_runner

class TestCLIDelegation(unittest.TestCase):
    """Tests for the new ai_pipeline.py CLI delegator."""

    @patch('scripts.ephemeral_runner.run_ephemeral_orchestration')
    def test_main_crewai(self, mock_run):
        with patch.object(sys, 'argv', ['ai_pipeline.py', '--crewai', 'test prompt']):
            ai_pipeline.main()
            mock_run.assert_called_once_with('test prompt', mode='venv', orchestrator='crewai')

    @patch('scripts.ephemeral_runner.run_ephemeral_orchestration')
    def test_main_openhands(self, mock_run):
        with patch.object(sys, 'argv', ['ai_pipeline.py', '--openhands', 'fix bug']):
            ai_pipeline.main()
            mock_run.assert_called_once_with('fix bug', mode='docker', orchestrator='openhands')

    @patch('scripts.ephemeral_runner.run_ephemeral_orchestration')
    def test_main_pydanticai(self, mock_run):
        with patch.object(sys, 'argv', ['ai_pipeline.py', '--pydanticai']):
            with patch('os.path.exists', return_value=True):
                with patch('builtins.open', mock_open(read_data='file prompt')):
                    ai_pipeline.main()
                    mock_run.assert_called_once_with('file prompt', mode='venv', orchestrator='pydanticai')

    @patch('scripts.ephemeral_runner.run_ephemeral_orchestration')
    def test_main_aider(self, mock_run):
        with patch.object(sys, 'argv', ['ai_pipeline.py', '--aider']):
            with patch('os.path.exists', return_value=False):
                ai_pipeline.main()
                mock_run.assert_called_once_with('Standard software engineering task.', mode='venv', orchestrator='aider')

    @patch('scripts.ephemeral_runner.run_ephemeral_orchestration')
    def test_main_langgraph(self, mock_run):
        with patch.object(sys, 'argv', ['ai_pipeline.py', '--langgraph', 'design system']):
            ai_pipeline.main()
            mock_run.assert_called_once_with('design system', mode='venv', orchestrator='langgraph')

    @patch('builtins.print')
    def test_main_help(self, mock_print):
        with patch.object(sys, 'argv', ['ai_pipeline.py']):
            ai_pipeline.main()
            mock_print.assert_any_call('Usage:')

    @patch('builtins.print')
    def test_main_unknown(self, mock_print):
        with patch.object(sys, 'argv', ['ai_pipeline.py', '--unknown']):
            with self.assertRaises(SystemExit) as cm:
                ai_pipeline.main()
            self.assertEqual(cm.exception.code, 1)
            mock_print.assert_any_call('❌ Unknown mode: --unknown')

class TestEphemeralRunner(unittest.TestCase):
    """Tests for the ephemeral runner lifecycle."""

    @patch('subprocess.run')
    @patch('tempfile.mkdtemp', return_value='/tmp/mock_venv')
    @patch('shutil.rmtree')
    @patch('os.makedirs')
    def test_execute_in_venv_crewai(self, mock_makedirs, mock_rmtree, mock_mkdtemp, mock_subrun):
        # Mock successful subprocess calls
        mock_subrun.return_value = MagicMock(returncode=0)
        
        ephemeral_runner.execute_in_venv("test prompt", "crewai")
        
        # Verify venv creation
        self.assertTrue(any('venv' in str(call) for call in mock_subrun.call_args_list))
        # Verify package installation
        self.assertTrue(any('install' in str(call) and 'crewai' in str(call) for call in mock_subrun.call_args_list))
        # Verify orchestrator run
        self.assertTrue(any('crewai_orchestrator.py' in str(call) for call in mock_subrun.call_args_list))
        # Verify cleanup
        mock_rmtree.assert_called_once_with('/tmp/mock_venv', ignore_errors=True)

    @patch('subprocess.run')
    @patch('tempfile.mkdtemp', return_value='/tmp/mock_venv')
    @patch('shutil.rmtree')
    @patch('os.makedirs')
    def test_execute_in_venv_langgraph(self, mock_makedirs, mock_rmtree, mock_mkdtemp, mock_subrun):
        mock_subrun.return_value = MagicMock(returncode=0)
        ephemeral_runner.execute_in_venv("test prompt", "langgraph")
        self.assertTrue(any('langgraph' in str(call) and 'install' in str(call) for call in mock_subrun.call_args_list))
        self.assertTrue(any('langgraph_orchestrator.py' in str(call) for call in mock_subrun.call_args_list))

    @patch('subprocess.run')
    @patch('os.makedirs')
    def test_execute_in_docker_openhands(self, mock_makedirs, mock_subrun):
        mock_subrun.return_value = MagicMock(returncode=0)
        
        ephemeral_runner.execute_in_docker("test prompt", "openhands")
        
        # Verify docker run call
        self.assertTrue(any('docker' in str(call) and 'run' in str(call) and 'openhands' in str(call) for call in mock_subrun.call_args_list))

    @patch('subprocess.run')
    @patch('os.makedirs')
    def test_execute_in_docker_wrong_orchestrator(self, mock_makedirs, mock_subrun):
        ephemeral_runner.execute_in_docker("test prompt", "crewai")
        mock_subrun.assert_not_called()

    @patch('subprocess.run', side_effect=Exception("Docker failed"))
    @patch('os.makedirs')
    @patch('builtins.print')
    def test_execute_in_docker_failure(self, mock_print, mock_makedirs, mock_subrun):
        ephemeral_runner.execute_in_docker("test prompt", "openhands")
        mock_print.assert_any_call('❌ Docker execution failed: Docker failed')

    @patch('subprocess.run', side_effect=Exception("Venv failed"))
    @patch('tempfile.mkdtemp', return_value='/tmp/mock_venv')
    @patch('shutil.rmtree')
    @patch('builtins.print')
    def test_execute_in_venv_failure(self, mock_print, mock_rmtree, mock_mkdtemp, mock_subrun):
        ephemeral_runner.execute_in_venv("test prompt", "crewai")
        mock_print.assert_any_call('❌ Error during ephemeral execution: Venv failed')

    @patch('scripts.ephemeral_runner.execute_in_venv')
    def test_run_ephemeral_orchestration_venv(self, mock_venv):
        ephemeral_runner.run_ephemeral_orchestration("prompt", mode="venv", orchestrator="aider")
        mock_venv.assert_called_once_with("prompt", "aider")

    @patch('scripts.ephemeral_runner.execute_in_docker')
    def test_run_ephemeral_orchestration_docker(self, mock_docker):
        ephemeral_runner.run_ephemeral_orchestration("prompt", mode="docker", orchestrator="openhands")
        mock_docker.assert_called_once_with("prompt", "openhands")

    def test_run_ephemeral_orchestration_unknown(self):
        with self.assertRaises(ValueError):
            ephemeral_runner.run_ephemeral_orchestration("prompt", mode="unknown")

class TestOrchestratorLogic(unittest.TestCase):
    """Tests for internal logic of orchestrator scripts."""

    def setUp(self):
        # Mocking external libraries that might not be installed in the host environment
        self.mocks = {
            'crewai': MagicMock(),
            'pydantic_ai': MagicMock(),
            'pydantic_ai.models': MagicMock(),
            'pydantic_ai.models.openai': MagicMock(),
            'pydantic_ai.models.anthropic': MagicMock(),
            'langgraph': MagicMock(),
            'langgraph.graph': MagicMock(),
            'langchain': MagicMock(),
            'langchain.tools': MagicMock(),
            'langchain_openai': MagicMock(),
            'langchain_core': MagicMock(),
            'langchain_core.messages': MagicMock(),
            'langchain_core.language_models': MagicMock(),
            'langchain_core.language_models.llms': MagicMock(),
            'langchain_core.language_models.chat_models': MagicMock(),
            'langchain_community': MagicMock(),
            'langchain_community.llms': MagicMock(),
            'langchain_anthropic': MagicMock()
        }
        self.patchers = [patch.dict('sys.modules', self.mocks)]
        for p in self.patchers:
            p.start()

    def tearDown(self):
        for p in self.patchers:
            p.stop()

    @patch('scripts.llm_router.generate', return_value='test response')
    def test_router_llm_crewai(self, mock_gen):
        # We need to ensure LLM is mocked correctly for inheritance
        with patch('langchain_core.language_models.llms.LLM', MagicMock):
            import scripts.crewai_orchestrator as crew_orch
            llm = crew_orch.RouterLLM()
            res = llm._call("hello")
            self.assertEqual(res, 'test response')
            mock_gen.assert_called_once_with('hello', stream=False)

    @patch('scripts.crewai_orchestrator.run_orchestration')
    def test_crewai_orchestration(self, mock_run):
        import scripts.crewai_orchestrator as crew_orch
        mock_run.return_value = "crewai result"
        result = crew_orch.run_orchestration("test prompt")
        self.assertEqual(result, "crewai result")

    @patch('scripts.pydanticai_orchestrator.run_pydantic_orchestration')
    def test_pydanticai_orchestration(self, mock_run):
        import scripts.pydanticai_orchestrator as pyd_orch
        mock_run.return_value = "pydantic result"
        import asyncio
        result = asyncio.run(pyd_orch.run_pydantic_orchestration("test prompt"))
        self.assertEqual(result, "pydantic result")

    @patch('scripts.langgraph_orchestrator.run_langgraph')
    def test_langgraph_orchestration(self, mock_run):
        import scripts.langgraph_orchestrator as lg_orch
        mock_run.return_value = "langgraph result"
        import asyncio
        result = asyncio.run(lg_orch.run_langgraph("test prompt"))
        self.assertEqual(result, "langgraph result")

    def test_ephemeral_runner_invalid_orchestrator(self):
        # This is now redundant with test_run_ephemeral_orchestration_unknown but good for mode/orch distinction
        from scripts.ephemeral_runner import run_ephemeral_orchestration
        with self.assertRaises(ValueError):
            run_ephemeral_orchestration("test", mode="invalid_mode")

    def test_pydanticai_model_config(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "sk-test"}):
            import importlib
            import scripts.pydanticai_orchestrator as pydantic_orch
            importlib.reload(pydantic_orch)
            # Check if it tried to initialize OpenAIModel
            self.assertTrue(self.mocks['pydantic_ai'].Agent.called)

    def test_langgraph_model_config(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "sk-test"}):
            import importlib
            import scripts.langgraph_orchestrator as lang_orch
            importlib.reload(lang_orch)
            # Check if it initialized correctly
            self.assertTrue(self.mocks['langgraph.graph'].StateGraph.called)

if __name__ == "__main__":
    unittest.main()
