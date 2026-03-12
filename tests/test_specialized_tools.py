import os
import sys
import unittest
import json
import shutil
from unittest.mock import patch, MagicMock, mock_open

# Add repo root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import scripts.rag_engine as rag_engine
import scripts.repo_map as repo_map
import scripts.visual_qa as visual_qa
import scripts.select_model as select_model
import scripts.mcp_client as mcp_client

class TestSpecializedTools(unittest.TestCase):

    # --- RAG Engine Tests ---
    def test_chunk_text(self):
        text = "Hello world. This is a test. Another sentence here."
        chunks = rag_engine.chunk_text(text, chunk_size=20, overlap=1)
        self.assertTrue(len(chunks) > 1)

    @patch('builtins.open', new_callable=mock_open, read_data="Technical documentation content.")
    @patch('os.walk')
    @patch('os.path.exists')
    def test_rag_indexing(self, mock_exists, mock_walk, mock_file):
        mock_exists.return_value = True
        mock_walk.return_value = [('root', [], ['doc.md'])]
        
        rag = rag_engine.RAGEngine(docs_dir="docs")
        count = rag.index()
        self.assertEqual(count, 1)
        
        context = rag.retrieve("Technical")
        self.assertIn("REFERENCE DOCUMENTS", context)
        self.assertIn("Technical", context)

    # --- Repo Map Tests ---
    @patch('builtins.open', new_callable=mock_open, read_data="class MyClass:\n    def my_method(self):\n        pass")
    def test_generate_python_map(self, mock_file):
        outline = repo_map._generate_python_map("test.py")
        self.assertIn("class MyClass", outline)
        self.assertIn("def my_method", outline)

    @patch('os.walk')
    @patch('os.path.exists')
    @patch('scripts.repo_map._parse_file')
    def test_generate_repo_map(self, mock_parse, mock_exists, mock_walk):
        mock_exists.return_value = True
        mock_walk.return_value = [('.', [], ['main.py'])]
        mock_parse.return_value = ("--- FILE: main.py ---", "class App")
        
        result = repo_map.generate_repo_map(".")
        self.assertIn("--- FILE: main.py ---", result)

    # --- Visual QA Tests ---
    @patch('glob.glob')
    def test_find_html_files(self, mock_glob):
        mock_glob.return_value = ['index.html']
        files = visual_qa.find_html_files(".")
        self.assertEqual(files, ['index.html'])

    @patch('requests.post')
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data=b"fake image data")
    def test_assess_with_vlm(self, mock_file, mock_exists, mock_post):
        mock_exists.return_value = True
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"response": "PASS: Looks great"}
        
        result = visual_qa.assess_with_vlm("screenshot.png")
        self.assertTrue(result['passed'])
        self.assertIn("Looks great", result['feedback'])

    # --- Select Model Tests ---
    @patch('scripts.select_model.get_total_memory_gb', return_value=16.0)
    @patch('scripts.select_model.get_gpu_vram_gb', return_value=8.0)
    def test_select_optimal_model(self, mock_vram, mock_ram):
        model = select_model.select_optimal_model()
        self.assertEqual(model, "qwen2.5-coder:7b")

    # --- MCP Client Tests ---
    @patch('scripts.llm_router.generate', return_value="mcp result")
    def test_mcp_execute_local_inference(self, mock_gen):
        res = mcp_client._mcp_execute_local_inference("test prompt")
        self.assertIn("mcp result", res)

    @patch('subprocess.run')
    def test_mcp_run_shell_command(self, mock_subrun):
        mock_subrun.return_value = MagicMock(stdout="shell output", stderr="", returncode=0)
        res = mcp_client._mcp_run_shell_command("ls")
        self.assertEqual(res, "shell output")

if __name__ == "__main__":
    unittest.main()
