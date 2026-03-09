import json
import os
import subprocess
import unittest
from unittest.mock import patch, MagicMock

import scripts.mcp_client as mcp_client

class TestMCPClient(unittest.TestCase):

    def test_format_mcp_tools(self):
        schema_str = mcp_client.format_mcp_tools_for_prompt()
        self.assertIsInstance(schema_str, str)
        parsed = json.loads(schema_str)
        self.assertIsInstance(parsed, list)
        self.assertGreater(len(parsed), 0)
        names = [tool["name"] for tool in parsed]
        self.assertIn("execute_local_inference", names)
        self.assertIn("run_shell_command", names)

    def test_execute_mcp_tool_invalid_json(self):
        result = mcp_client.execute_mcp_tool("run_shell_command", "{bad json}")
        self.assertIn("Error: Failed to parse tool arguments as JSON", result)

    def test_execute_mcp_tool_unknown(self):
        result = mcp_client.execute_mcp_tool("fake_tool", '{"foo": "bar"}')
        self.assertIn("Error: Unknown MCP tool 'fake_tool'", result)

    @patch('scripts.llm_router.generate')
    @patch.dict(os.environ, {"LLM_PROVIDER": "openai", "OLLAMA_MODEL": "default-model"}, clear=True)
    def test_mcp_execute_local_inference(self, mock_generate):
        mock_generate.return_value = "Mocked LLM Response"
        
        # Test routing and execution
        result = mcp_client.execute_mcp_tool(
            "execute_local_inference", 
            '{"prompt": "Hello", "model": "llama3.2"}'
        )
        
        self.assertIn("Local GPU Output:", result)
        self.assertIn("Mocked LLM Response", result)
        
        # Ensure it restored the environment properly
        self.assertEqual(os.environ.get("LLM_PROVIDER"), "openai")
        self.assertEqual(os.environ.get("OLLAMA_MODEL"), "default-model")
        mock_generate.assert_called_once_with("Hello")

    @patch('subprocess.run')
    def test_mcp_run_shell_command_success(self, mock_run):
        mock_result = MagicMock()
        mock_result.stdout = "Found 3 files"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        result = mcp_client.execute_mcp_tool(
            "run_shell_command",
            '{"command": "ls -l"}'
        )
        
        self.assertEqual(result, "Found 3 files")
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        self.assertEqual(args[0], "ls -l")
        self.assertTrue(kwargs.get("shell"))

    @patch('subprocess.run')
    def test_mcp_run_shell_command_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="sleep 100", timeout=60)
        
        result = mcp_client.execute_mcp_tool(
            "run_shell_command",
            '{"command": "sleep 100"}'
        )
        
        self.assertIn("Error: Command timed out", result)

    @patch('subprocess.run')
    def test_mcp_run_shell_command_stderr(self, mock_run):
        mock_result = MagicMock()
        mock_result.stdout = "Output"
        mock_result.stderr = "Some warning"
        mock_run.return_value = mock_result

        result = mcp_client.execute_mcp_tool(
            "run_shell_command",
            '{"command": "ls -l"}'
        )
        
        self.assertIn("Output", result)
        self.assertIn("--- STDERR ---", result)
        self.assertIn("Some warning", result)

if __name__ == '__main__':
    unittest.main()
