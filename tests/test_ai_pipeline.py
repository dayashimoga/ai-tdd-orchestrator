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

    @patch('builtins.open', new_callable=mock_open)
    @patch('scripts.ai_pipeline.ai_generate', return_value="- [ ] Task 1")
    @patch('builtins.print')
    def test_generate_task_plan(self, mock_print, mock_generate, mock_file):
        ai_pipeline.generate_task_plan("Do something")
        mock_file.assert_called_with("your_project/project_tasks.md", "w")
        mock_file().write.assert_called_with("- [ ] Task 1")

    @patch('os.walk', return_value=[('your_project', (), ('app.py',))])
    @patch('builtins.open', new_callable=mock_open, read_data="code here")
    @patch('os.makedirs')
    @patch('scripts.ai_pipeline.ai_generate', return_value="--- FILE: test.py ---\nprint('ok')")
    def test_execute_task(self, mock_gen, mock_mkdir, mock_file, mock_walk):
        ai_pipeline.execute_task("Build it")
        mock_file.assert_any_call(os.path.join("your_project", "test.py"), "w", encoding='utf-8')
        mock_file().write.assert_any_call("print('ok')")

    @patch('subprocess.run')
    def test_run_pytest_validation_success(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Coverage Achieved"
        mock_run.return_value = mock_result
        success, output = ai_pipeline.run_pytest_validation()
        self.assertTrue(success)
        self.assertEqual(output, "Coverage Achieved")

    @patch('subprocess.run')
    def test_run_pytest_validation_failure(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "Coverage Failed"
        mock_result.stderr = "Traceback"
        mock_run.return_value = mock_result
        success, output = ai_pipeline.run_pytest_validation()
        self.assertFalse(success)
        self.assertTrue("Coverage Failed" in output)

    @patch('subprocess.run', side_effect=Exception("Subprocess Error"))
    def test_run_pytest_validation_exception(self, mock_run):
        success, output = ai_pipeline.run_pytest_validation()
        self.assertFalse(success)
        self.assertEqual(output, "Subprocess Error")

    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data="- [ ] Task 1\n- [x] Task 2")
    @patch('scripts.ai_pipeline.execute_task')
    @patch('scripts.ai_pipeline.run_pytest_validation', return_value=(True, "OK"))
    def test_run_tdd_loop_success(self, mock_pytest, mock_execute, mock_file, mock_exists):
        # The loop reads, finds the uncompleted task, executes, passes tests, and writes back [x]
        ai_pipeline.run_tdd_loop(max_iterations=1)
        mock_execute.assert_called_once_with("Task 1")
        mock_file().writelines.assert_called()

    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data="- [ ] Task 1")
    @patch('scripts.ai_pipeline.execute_task')
    @patch('scripts.ai_pipeline.run_pytest_validation', return_value=(False, "Failed!"))
    def test_run_tdd_loop_failure(self, mock_pytest, mock_execute, mock_file, mock_exists):
        # Task execution fails, loops back execution with bug context
        ai_pipeline.run_tdd_loop(max_iterations=1)
        # Should be called twice (the initial task, and then the retry attempt fed with stack trace)
        self.assertEqual(mock_execute.call_count, 2)

    @patch('os.path.exists', return_value=False)
    def test_run_tdd_loop_no_file(self, mock_exists):
        # Should gracefully exit loop if file doesn't exist
        ai_pipeline.run_tdd_loop()

    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data="- [x] Task 1\n- [x] Task 2")
    def test_run_tdd_loop_all_done(self, mock_file, mock_exists):
        # Should exit immediately if all tasks are complete
        ai_pipeline.run_tdd_loop()

    @patch('sys.argv', ['ai_pipeline.py'])
    @patch('builtins.print')
    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data="Dummy Prompt")
    def test_main_execution_standard(self, mock_file, mock_exists, mock_print):
        ai_pipeline.main()
        mock_print.assert_any_call("Dummy Prompt")
        mock_print.assert_any_call("Standard static review pipeline disabled in favor of TDD Orchestrator.")

    @patch('sys.argv', ['ai_pipeline.py', '--manual'])
    @patch('scripts.ai_pipeline.ensure_code_exists')
    @patch('scripts.ai_pipeline.generate_task_plan')
    @patch('scripts.ai_pipeline.run_tdd_loop')
    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data="Task Prompt")
    def test_main_execution_manual(self, mock_file, mock_exists, mock_tdd, mock_plan, mock_ensure):
        ai_pipeline.main()
        mock_ensure.assert_called_once()
        mock_plan.assert_called_once_with("Task Prompt")
        mock_tdd.assert_called_once()

if __name__ == '__main__':
    unittest.main()
