import sys
import os
import unittest
from unittest.mock import patch, mock_open, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import scripts.ai_pipeline as ai_pipeline

class TestAIPipeline(unittest.TestCase):

    @patch('requests.post')
    def test_ai_generate_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {'response': 'test output'}
        mock_post.return_value = mock_response
        self.assertEqual(ai_pipeline.ai_generate("prompt"), "test output")

    @patch('requests.post', side_effect=Exception("API Error"))
    def test_ai_generate_failure(self, mock_post):
        self.assertEqual(ai_pipeline.ai_generate("prompt"), "")

    @patch('scripts.ai_pipeline.IS_LOCAL', True)
    @patch('builtins.print')
    def test_post_inline_comment_local(self, mock_print):
        ai_pipeline.post_inline_comment("file.py", 10, "comment")
        mock_print.assert_called_with("\n[Local Review] file.py:10 -> comment\n")

    @patch('scripts.ai_pipeline.IS_LOCAL', False)
    @patch('scripts.ai_pipeline.GITHUB_TOKEN', 'token')
    @patch('scripts.ai_pipeline.PR_NUMBER', '1')
    @patch('scripts.ai_pipeline.REPO_NAME', 'repo')
    @patch('scripts.ai_pipeline.COMMIT_SHA', 'sha')
    @patch('scripts.ai_pipeline.Github')
    def test_post_inline_comment_ci(self, mock_github):
        mock_pr = MagicMock()
        mock_github.return_value.get_repo.return_value.get_pull.return_value = mock_pr
        ai_pipeline.post_inline_comment("file.py", 10, "comment")
        mock_pr.create_review_comment.assert_called_once()

    @patch('scripts.ai_pipeline.IS_LOCAL', False)
    @patch('subprocess.check_output', return_value="your_project/new.py\nyour_project/style.css\n")
    def test_get_modified_files(self, mock_sub):
        self.assertEqual(ai_pipeline.get_modified_files(), ["your_project/new.py", "your_project/style.css"])

    @patch('subprocess.getoutput')
    def test_run_critic(self, mock_getoutput):
        mock_getoutput.side_effect = ["pylint error", "bandit error", "eslint error", "njsscan error", "golint error", "gosec error", "html error", "css error", "eslint ts error"]
        self.assertEqual(ai_pipeline.run_critic("f.py", "Python"), "pylint error\nbandit error\n")
        self.assertEqual(ai_pipeline.run_critic("f.js", "JavaScript"), "eslint error\nnjsscan error\n")
        self.assertEqual(ai_pipeline.run_critic("f.go", "Go"), "golint error\ngosec error\n")
        self.assertEqual(ai_pipeline.run_critic("f.html", "HTML"), "html error\n")
        self.assertEqual(ai_pipeline.run_critic("f.css", "CSS"), "css error\n")
        self.assertEqual(ai_pipeline.run_critic("f.ts", "TypeScript"), "eslint ts error\n")

    @patch('builtins.open', new_callable=mock_open)
    @patch('scripts.ai_pipeline.ai_generate', return_value="```python\nfixed_code()\n```")
    def test_run_engineer(self, mock_generate, mock_file):
        fixed = ai_pipeline.run_engineer("f.py", "bad_code()", "error", "Python")
        self.assertEqual(fixed, "fixed_code()")
        mock_file().write.assert_called_with("fixed_code()")

    @patch('scripts.ai_pipeline.post_inline_comment')
    @patch('scripts.ai_pipeline.ai_generate', return_value="COMMENT_LINE: 5|Fixed security bug")
    def test_run_reviewer(self, mock_generate, mock_post):
        ai_pipeline.run_reviewer("f.py", "bad", "good", "Python")
        mock_post.assert_called_with("f.py", 5, "Fixed security bug")

    @patch('scripts.ai_pipeline.get_modified_files', return_value=["your_project/app.py"])
    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data="bad_code")
    @patch('scripts.ai_pipeline.run_critic', side_effect=["error", "clear"])
    @patch('scripts.ai_pipeline.run_engineer', return_value="good_code")
    @patch('scripts.ai_pipeline.run_reviewer')
    @patch('scripts.ai_pipeline.ensure_code_exists')
    def test_run_pipeline(self, mock_ensure, mock_reviewer, mock_eng, mock_critic, mock_file, mock_exists, mock_get):
        ai_pipeline.run_pipeline(max_iterations=2)
        mock_critic.assert_called()
        mock_eng.assert_called_once()
        mock_reviewer.assert_called_once()

    @patch('os.walk', return_value=[('your_project', (), ())])
    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data="prompt")
    @patch('os.makedirs')
    @patch('scripts.ai_pipeline.ai_generate', return_value="--- FILE: index.html ---\n<h1>Hello</h1>\n--- FILE: css/style.css ---\ncolor: red;")
    def test_ensure_code_exists_multi_file(self, mock_gen, mock_mkdir, mock_file, mock_exists, mock_walk):
        ai_pipeline.ensure_code_exists()
        mock_gen.assert_called_once()
        # Ensure os.makedirs was called for subdirectories and root
        mock_mkdir.assert_any_call("your_project", exist_ok=True)
        # Ensure it wrote to multiple files based on the parsed delimiters
        mock_file.assert_any_call(os.path.join("your_project", "index.html"), "w")
        mock_file().write.assert_any_call("<h1>Hello</h1>")
        mock_file.assert_any_call(os.path.join("your_project", "css", "style.css"), "w")
        mock_file().write.assert_any_call("color: red;")

    @patch('os.walk', return_value=[('your_project', (), ())])
    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data="prompt")
    @patch('os.makedirs')
    @patch('scripts.ai_pipeline.ai_generate', return_value="Just some bad plain code response without delimiters")
    def test_ensure_code_exists_fallback(self, mock_gen, mock_mkdir, mock_file, mock_exists, mock_walk):
        ai_pipeline.ensure_code_exists()
        # Ensure fallback file was created
        mock_file.assert_any_call("your_project/generated_code.txt", "w")
        mock_file().write.assert_any_call("Just some bad plain code response without delimiters")

    @patch('sys.argv', ['ai_pipeline.py'])
    @patch('scripts.ai_pipeline.run_pipeline')
    def test_main_execution(self, mock_run):
        ai_pipeline.main()
        mock_run.assert_called_once()

if __name__ == '__main__':
    unittest.main()
