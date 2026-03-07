import sys
import os
import subprocess
import unittest
from unittest.mock import patch, mock_open, MagicMock, call

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import scripts.ai_pipeline as ai_pipeline


class TestUtilities(unittest.TestCase):
    """Tests for shared utility functions."""

    def test_mask_secret(self):
        self.assertEqual(ai_pipeline.mask_secret("token=abc123xyz", "abc123xyz"), "token=***")

    def test_mask_secret_short(self):
        self.assertEqual(ai_pipeline.mask_secret("short", "ab"), "short")

    def test_mask_secret_none(self):
        self.assertEqual(ai_pipeline.mask_secret("text", None), "text")

    def test_safe_path_valid(self):
        with patch('os.path.realpath', side_effect=lambda p: os.path.join(os.getcwd(), p)):
            result = ai_pipeline.safe_path("your_project/main.py", "your_project")
            self.assertIsNotNone(result)

    def test_safe_path_traversal(self):
        result = ai_pipeline.safe_path("../../etc/passwd", "your_project")
        self.assertIsNone(result)

    def test_truncate_feedback_short(self):
        result = ai_pipeline.truncate_feedback("line1\nline2\nline3")
        self.assertEqual(result, "line1\nline2\nline3")

    def test_truncate_feedback_long(self):
        long_output = "\n".join([f"line{i}" for i in range(100)])
        result = ai_pipeline.truncate_feedback(long_output, max_lines=10)
        lines = result.strip().split("\n")
        self.assertEqual(len(lines), 10)

    def test_truncate_feedback_ansi(self):
        ansi_text = "\x1b[31mERROR\x1b[0m: something failed"
        result = ai_pipeline.truncate_feedback(ansi_text)
        self.assertNotIn("\x1b", result)
        self.assertIn("ERROR", result)

    def test_parse_and_write_files(self):
        raw = "--- FILE: test.py ---\nprint('hello')\n--- FILE: test2.py ---\nprint('world')"
        with patch('scripts.ai_pipeline.safe_path', return_value="your_project/test.py"):
            with patch('os.makedirs'):
                with patch('builtins.open', mock_open()):
                    count = ai_pipeline.parse_and_write_files(raw, "your_project")
                    self.assertEqual(count, 2)

    def test_parse_and_write_files_empty(self):
        count = ai_pipeline.parse_and_write_files("Just some text", "your_project")
        self.assertEqual(count, 0)

    def test_get_github_client(self):
        with patch('scripts.ai_pipeline.Github') as mock_gh:
            ai_pipeline.get_github_client("token123")
            mock_gh.assert_called_with("token123")

    def test_git_run(self):
        with patch('subprocess.run') as mock_run:
            ai_pipeline.git_run(["git", "status"])
            mock_run.assert_called_once()
            # Verify timeout is passed
            call_kwargs = mock_run.call_args[1]
            self.assertEqual(call_kwargs['timeout'], 120)


class TestAIGenerate(unittest.TestCase):
    """Tests for LLM API interaction."""

    @patch('requests.post')
    def test_ai_generate_success(self, mock_post):
        import json
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = [
            json.dumps({"response": "hello "}).encode(),
            json.dumps({"response": "world"}).encode(),
        ]
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        result = ai_pipeline.ai_generate("test prompt")
        self.assertEqual(result, "hello world")

    @patch('requests.post', side_effect=Exception("Connection refused"))
    def test_ai_generate_failure(self, mock_post):
        result = ai_pipeline.ai_generate("test prompt")
        self.assertEqual(result, "")


class TestRepositoryManagement(unittest.TestCase):
    """Tests for setup_target_repository and push_to_target_repository."""

    @patch('scripts.ai_pipeline.TARGET_REPO', '')
    @patch('builtins.print')
    def test_setup_no_target(self, mock_print):
        ai_pipeline.setup_target_repository()
        mock_print.assert_any_call("⚠️ No TARGET_REPO provided. Operating locally in 'your_project'.")

    @patch('scripts.ai_pipeline.TARGET_REPO', 'test/repo')
    @patch('scripts.ai_pipeline.PROJECT_TYPE', 'existing')
    @patch('scripts.ai_pipeline.TARGET_REPO_TOKEN', 'token')
    @patch('scripts.ai_pipeline.git_run')
    @patch('os.path.exists', return_value=False)
    @patch('builtins.print')
    def test_setup_existing(self, mock_print, mock_exists, mock_git):
        ai_pipeline.setup_target_repository()
        mock_print.assert_any_call("✅ Clone complete.")

    @patch('scripts.ai_pipeline.TARGET_REPO', 'test/repo')
    @patch('scripts.ai_pipeline.PROJECT_TYPE', 'new')
    @patch('scripts.ai_pipeline.TARGET_REPO_TOKEN', 'token')
    @patch('scripts.ai_pipeline.get_github_client')
    @patch('scripts.ai_pipeline.git_run')
    @patch('os.path.exists', return_value=False)
    @patch('os.makedirs')
    @patch('builtins.open', new_callable=mock_open)
    @patch('builtins.print')
    def test_setup_new(self, mock_print, mock_file, mock_makedirs, mock_exists, mock_git, mock_gh):
        ai_pipeline.setup_target_repository()
        mock_gh.return_value.get_user.return_value.create_repo.assert_called_once()

    @patch('scripts.ai_pipeline.TARGET_REPO', 'test/repo')
    @patch('scripts.ai_pipeline.PROJECT_TYPE', 'new')
    @patch('scripts.ai_pipeline.TARGET_REPO_TOKEN', 'token')
    @patch('scripts.ai_pipeline.get_github_client')
    @patch('os.path.exists', return_value=False)
    @patch('os.makedirs')
    @patch('sys.exit')
    @patch('builtins.print')
    def test_setup_new_failure(self, mock_print, mock_exit, mock_makedirs, mock_exists, mock_gh):
        mock_gh.return_value.get_user.return_value.create_repo.side_effect = Exception("403 Forbidden")
        mock_exit.side_effect = SystemExit
        with self.assertRaises(SystemExit):
            ai_pipeline.setup_target_repository()
        mock_exit.assert_called_with(1)

    @patch('scripts.ai_pipeline.TARGET_REPO', '')
    def test_push_no_target(self):
        ai_pipeline.push_to_target_repository()  # Should just return

    @patch('scripts.ai_pipeline.TARGET_REPO', 'test/repo')
    @patch('scripts.ai_pipeline.TARGET_REPO_TOKEN', 'token')
    @patch('scripts.ai_pipeline.git_run')
    @patch('builtins.print')
    def test_push_no_changes(self, mock_print, mock_git):
        mock_status = MagicMock()
        mock_status.stdout = ""
        mock_git.return_value = mock_status
        ai_pipeline.push_to_target_repository()
        mock_print.assert_any_call("✅ No changes to commit.")

    @patch('scripts.ai_pipeline.TARGET_REPO', 'test/repo')
    @patch('scripts.ai_pipeline.TARGET_REPO_TOKEN', 'token')
    @patch('scripts.ai_pipeline.git_run')
    @patch('builtins.print')
    def test_push_with_changes(self, mock_print, mock_git):
        mock_status = MagicMock()
        mock_status.stdout = " M file.py"
        mock_git.return_value = mock_status
        ai_pipeline.push_to_target_repository()
        self.assertTrue(mock_git.call_count >= 5)


class TestTDDLoop(unittest.TestCase):
    """Tests for generate_task_plan, execute_task, run_pytest_validation, and run_tdd_loop."""

    @patch('scripts.ai_pipeline.ai_generate', return_value="- [ ] Task 1\n- [ ] Task 2")
    @patch('builtins.open', new_callable=mock_open)
    @patch('builtins.print')
    def test_generate_task_plan(self, mock_print, mock_file, mock_gen):
        ai_pipeline.generate_task_plan("Build a calculator")
        mock_gen.assert_called_once()

    @patch('scripts.ai_pipeline.ai_generate', return_value="--- FILE: main.py ---\nprint('hi')")
    @patch('scripts.ai_pipeline.repo_map')
    @patch('scripts.ai_pipeline.parse_and_write_files', return_value=1)
    @patch('requests.post')
    @patch('builtins.print')
    def test_execute_task(self, mock_print, mock_post, mock_parse, mock_rmap, mock_gen):
        mock_rmap.generate_repo_map.return_value = "class Foo: ..."
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "NONE"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp
        ai_pipeline.execute_task("Implement main module")

    @patch('subprocess.run')
    @patch('builtins.print')
    def test_run_pytest_validation_pass(self, mock_print, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="All passed", stderr="")
        success, feedback = ai_pipeline.run_pytest_validation()
        self.assertTrue(success)

    @patch('subprocess.run')
    @patch('builtins.print')
    def test_run_pytest_validation_fail(self, mock_print, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="FAILED", stderr="Error")
        success, feedback = ai_pipeline.run_pytest_validation()
        self.assertFalse(success)

    @patch('subprocess.run', side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=120))
    @patch('builtins.print')
    def test_run_pytest_timeout(self, mock_print, mock_run):
        success, feedback = ai_pipeline.run_pytest_validation()
        self.assertFalse(success)
        self.assertIn("timed out", feedback)

    def test_save_rollback_point(self):
        with patch('scripts.ai_pipeline.git_run') as mock_git:
            mock_git.return_value = MagicMock(stdout="abc123def")
            result = ai_pipeline.save_rollback_point()
            self.assertEqual(result, "abc123def")

    def test_rollback_if_worse(self):
        with patch('scripts.ai_pipeline.git_run') as mock_git:
            with patch('builtins.print'):
                ai_pipeline.rollback_if_worse("abc123", False)
                mock_git.assert_called_once()

    def test_rollback_skipped_on_success(self):
        with patch('scripts.ai_pipeline.git_run') as mock_git:
            ai_pipeline.rollback_if_worse("abc123", True)
            mock_git.assert_not_called()


class TestIssueResolver(unittest.TestCase):
    """Tests for resolve_issue."""

    @patch('scripts.ai_pipeline.setup_target_repository')
    @patch('scripts.ai_pipeline.generate_task_plan')
    @patch('scripts.ai_pipeline.run_tdd_loop')
    @patch('scripts.ai_pipeline.git_run')
    @patch('scripts.ai_pipeline.get_github_client')
    def test_resolve_issue_success(self, mock_gh, mock_git, mock_tdd, mock_plan, mock_setup):
        with patch.dict(os.environ, {"ISSUE_NUMBER": "1", "ISSUE_TITLE": "Bug", "ISSUE_BODY": "Fix it", "REPO_NAME": "org/repo", "TARGET_REPO_TOKEN": "token"}):
            mock_status = MagicMock()
            mock_status.stdout = " M file.py"
            mock_git.return_value = mock_status
            ai_pipeline.resolve_issue()
            mock_gh.return_value.get_repo.return_value.create_pull.assert_called_once()

    @patch('sys.exit')
    @patch('builtins.print')
    def test_resolve_issue_missing_env(self, mock_print, mock_exit):
        mock_exit.side_effect = SystemExit
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit):
                ai_pipeline.resolve_issue()

    @patch('scripts.ai_pipeline.setup_target_repository')
    @patch('scripts.ai_pipeline.generate_task_plan')
    @patch('scripts.ai_pipeline.run_tdd_loop')
    @patch('scripts.ai_pipeline.git_run')
    @patch('builtins.print')
    @patch('sys.exit')
    def test_resolve_issue_no_changes(self, mock_exit, mock_print, mock_git, mock_tdd, mock_plan, mock_setup):
        mock_exit.side_effect = SystemExit
        mock_status = MagicMock()
        mock_status.stdout = ""
        mock_git.return_value = mock_status
        with patch.dict(os.environ, {"ISSUE_NUMBER": "1", "ISSUE_TITLE": "Bug", "ISSUE_BODY": "Fix", "REPO_NAME": "org/repo", "TARGET_REPO_TOKEN": "tok"}):
            with self.assertRaises(SystemExit):
                ai_pipeline.resolve_issue()
            mock_exit.assert_called_with(0)


class TestPRChat(unittest.TestCase):
    """Tests for post_help_comment and resume_with_hint."""

    @patch('scripts.ai_pipeline.get_github_client')
    def test_post_help_comment_success(self, mock_gh):
        with patch.dict(os.environ, {"PR_NUMBER": "1", "REPO_NAME": "org/repo", "GITHUB_TOKEN": "token"}):
            with patch('os.path.exists', return_value=False):
                ai_pipeline.post_help_comment()
                mock_gh.return_value.get_repo.return_value.get_pull.return_value.create_issue_comment.assert_called_once()

    @patch('builtins.print')
    def test_post_help_comment_no_env(self, mock_print):
        with patch.dict(os.environ, {}, clear=True):
            ai_pipeline.post_help_comment()
            mock_print.assert_any_call("💡 Tip: To enable interactive help, set GITHUB_TOKEN, PR_NUMBER, and REPO_NAME.")

    @patch('scripts.ai_pipeline.get_github_client')
    @patch('builtins.print')
    def test_post_help_comment_exception(self, mock_print, mock_gh):
        mock_gh.side_effect = Exception("API Error")
        with patch.dict(os.environ, {"PR_NUMBER": "1", "REPO_NAME": "org/repo", "GITHUB_TOKEN": "token"}):
            ai_pipeline.post_help_comment()
            mock_print.assert_any_call("⚠️ Could not post help comment: API Error")

    @patch('scripts.ai_pipeline.execute_task')
    @patch('scripts.ai_pipeline.run_pytest_validation', return_value=(True, "OK"))
    @patch('scripts.ai_pipeline.run_tdd_loop')
    @patch('scripts.ai_pipeline.push_to_target_repository')
    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data="- [ ] Task 1\n")
    def test_resume_with_hint_success(self, mock_file, mock_exists, mock_push, mock_tdd, mock_pytest, mock_exec):
        with patch.dict(os.environ, {"USER_HINT": "@ai-hint Use bcrypt"}):
            ai_pipeline.resume_with_hint()
            mock_exec.assert_called_once()
            mock_tdd.assert_called_once()

    @patch('builtins.print')
    def test_resume_with_hint_no_hint(self, mock_print):
        with patch.dict(os.environ, {"USER_HINT": ""}):
            ai_pipeline.resume_with_hint()
            mock_print.assert_any_call("❌ No USER_HINT environment variable provided.")

    @patch('os.path.exists', return_value=False)
    @patch('builtins.print')
    def test_resume_with_hint_no_tasks(self, mock_print, mock_exists):
        with patch.dict(os.environ, {"USER_HINT": "@ai-hint Fix bug"}):
            ai_pipeline.resume_with_hint()
            mock_print.assert_any_call("⚠️ No project_tasks.md found. Cannot resume.")


class TestMainCLI(unittest.TestCase):
    """Tests for main() CLI routing."""

    @patch('sys.argv', ['ai_pipeline.py', '--manual'])
    @patch('scripts.ai_pipeline.setup_target_repository')
    @patch('scripts.ai_pipeline.ensure_code_exists')
    @patch('scripts.ai_pipeline.generate_task_plan')
    @patch('scripts.ai_pipeline.run_tdd_loop')
    @patch('scripts.ai_pipeline.push_to_target_repository')
    @patch('os.path.exists', return_value=False)
    def test_main_manual(self, mock_exists, mock_push, mock_tdd, mock_plan, mock_ensure, mock_setup):
        ai_pipeline.main()
        mock_setup.assert_called_once()

    @patch('sys.argv', ['ai_pipeline.py', '--issue'])
    @patch('scripts.ai_pipeline.resolve_issue')
    @patch('os.path.exists', return_value=False)
    def test_main_issue(self, mock_exists, mock_resolve):
        ai_pipeline.main()
        mock_resolve.assert_called_once()

    @patch('sys.argv', ['ai_pipeline.py', '--resume-with-hint'])
    @patch('scripts.ai_pipeline.resume_with_hint')
    @patch('os.path.exists', return_value=False)
    def test_main_resume(self, mock_exists, mock_resume):
        ai_pipeline.main()
        mock_resume.assert_called_once()

    @patch('sys.argv', ['ai_pipeline.py'])
    @patch('builtins.print')
    @patch('os.path.exists', return_value=False)
    def test_main_default(self, mock_exists, mock_print):
        ai_pipeline.main()
        mock_print.assert_any_call("Standard static review pipeline disabled in favor of TDD Orchestrator.")


    @patch('scripts.ai_pipeline.ai_generate', return_value="no files here")
    @patch('scripts.ai_pipeline.parse_and_write_files', return_value=0)
    @patch('os.path.exists', return_value=True)
    @patch('os.walk', return_value=[])
    @patch('builtins.open', new_callable=mock_open, read_data="Build app")
    @patch('os.makedirs')
    @patch('builtins.print')
    def test_ensure_code_exists_fallback(self, mock_print, mock_makedirs, mock_file, mock_walk, mock_exists, mock_parse, mock_gen):
        ai_pipeline.ensure_code_exists()
        # Should write fallback file when parse_and_write returns 0


class TestGetModifiedFiles(unittest.TestCase):
    """Tests for get_modified_files."""

    @patch('scripts.ai_pipeline.IS_LOCAL', True)
    @patch('os.walk', return_value=[("your_project", [], ["main.py", "style.css"])])
    def test_get_modified_files_local(self, mock_walk):
        files = ai_pipeline.get_modified_files()
        self.assertEqual(len(files), 2)

    @patch('scripts.ai_pipeline.IS_LOCAL', False)
    @patch('subprocess.check_output', return_value="your_project/main.py\nyour_project/test.py\n")
    def test_get_modified_files_ci(self, mock_output):
        files = ai_pipeline.get_modified_files()
        self.assertEqual(len(files), 2)

    @patch('scripts.ai_pipeline.IS_LOCAL', False)
    @patch('subprocess.check_output', side_effect=Exception("git error"))
    @patch('os.walk', return_value=[("your_project", [], ["a.py"])])
    @patch('builtins.print')
    def test_get_modified_files_fallback(self, mock_print, mock_walk, mock_output):
        files = ai_pipeline.get_modified_files()
        self.assertTrue(len(files) >= 1)


class TestPostInlineComment(unittest.TestCase):
    """Tests for post_inline_comment."""

    @patch('scripts.ai_pipeline.IS_LOCAL', True)
    @patch('builtins.print')
    def test_inline_comment_local(self, mock_print):
        ai_pipeline.post_inline_comment("file.py", 10, "Fix this")
        mock_print.assert_any_call("\n[Local Review] file.py:10 -> Fix this\n")

    @patch('scripts.ai_pipeline.IS_LOCAL', False)
    @patch('scripts.ai_pipeline.GITHUB_TOKEN', 'token')
    @patch('scripts.ai_pipeline.PR_NUMBER', '1')
    @patch('scripts.ai_pipeline.REPO_NAME', 'org/repo')
    @patch('scripts.ai_pipeline.COMMIT_SHA', 'abc123')
    @patch('scripts.ai_pipeline.get_github_client')
    def test_inline_comment_github(self, mock_gh):
        ai_pipeline.post_inline_comment("file.py", 10, "Fix this")
        mock_gh.return_value.get_repo.return_value.get_pull.return_value.create_review_comment.assert_called_once()

    @patch('scripts.ai_pipeline.IS_LOCAL', False)
    @patch('scripts.ai_pipeline.GITHUB_TOKEN', 'token')
    @patch('scripts.ai_pipeline.PR_NUMBER', '1')
    @patch('scripts.ai_pipeline.REPO_NAME', 'org/repo')
    @patch('scripts.ai_pipeline.COMMIT_SHA', 'abc123')
    @patch('scripts.ai_pipeline.get_github_client', side_effect=Exception("API fail"))
    @patch('builtins.print')
    def test_inline_comment_error(self, mock_print, mock_gh):
        ai_pipeline.post_inline_comment("file.py", 10, "Fix this")
        mock_print.assert_any_call("Failed to post PR comment: API fail")


class TestTDDLoopBranches(unittest.TestCase):
    """Tests for run_tdd_loop branch coverage."""

    @patch('os.path.exists', return_value=False)
    @patch('builtins.print')
    def test_tdd_loop_no_tasks_file(self, mock_print, mock_exists):
        ai_pipeline.run_tdd_loop(max_iterations=1)

    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data="- [x] Done task\n")
    @patch('builtins.print')
    def test_tdd_loop_all_done(self, mock_print, mock_file, mock_exists):
        ai_pipeline.run_tdd_loop(max_iterations=1)
        mock_print.assert_any_call("\n==============================================")

    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data="- [ ] Build module\n")
    @patch('scripts.ai_pipeline.save_rollback_point', return_value="abc123")
    @patch('scripts.ai_pipeline.execute_task')
    @patch('scripts.ai_pipeline.run_pytest_validation', return_value=(True, "OK"))
    @patch('scripts.ai_pipeline.rollback_if_worse')
    @patch('builtins.print')
    def test_tdd_loop_task_passes(self, mock_print, mock_rollback, mock_pytest, mock_exec, mock_save, mock_file, mock_exists):
        ai_pipeline.run_tdd_loop(max_iterations=1)

    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data="- [ ] Build module\n")
    @patch('scripts.ai_pipeline.save_rollback_point', return_value="abc123")
    @patch('scripts.ai_pipeline.execute_task')
    @patch('scripts.ai_pipeline.run_pytest_validation', return_value=(False, "FAILED"))
    @patch('scripts.ai_pipeline.rollback_if_worse')
    @patch('scripts.ai_pipeline.post_help_comment')
    @patch('builtins.print')
    def test_tdd_loop_task_fails_exhausted(self, mock_print, mock_help, mock_rollback, mock_pytest, mock_exec, mock_save, mock_file, mock_exists):
        ai_pipeline.run_tdd_loop(max_iterations=1)
        mock_rollback.assert_called()

    @patch('subprocess.run', side_effect=Exception("No pytest found"))
    @patch('builtins.print')
    def test_run_pytest_exception(self, mock_print, mock_run):
        success, feedback = ai_pipeline.run_pytest_validation()
        self.assertFalse(success)


class TestGenerateTaskPlanWithSummary(unittest.TestCase):
    """Test generate_task_plan GitHub summary path."""

    @patch('scripts.ai_pipeline.ai_generate', return_value="- [ ] Task 1")
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists', return_value=True)
    @patch('os.getenv', return_value="summary.md")
    @patch('builtins.print')
    def test_generate_plan_with_summary(self, mock_print, mock_getenv, mock_exists, mock_file, mock_gen):
        ai_pipeline.generate_task_plan("Build a web app")


class TestExecuteTaskBranches(unittest.TestCase):
    """Test execute_task file loading branches."""

    @patch('scripts.ai_pipeline.ai_generate', return_value="--- FILE: main.py ---\ncode")
    @patch('scripts.ai_pipeline.repo_map')
    @patch('scripts.ai_pipeline.parse_and_write_files', return_value=1)
    @patch('requests.post')
    @patch('os.path.exists', return_value=True)
    @patch('os.path.isfile', return_value=True)
    @patch('scripts.ai_pipeline.safe_path', return_value="your_project/main.py")
    @patch('builtins.open', new_callable=mock_open, read_data="content")
    @patch('builtins.print')
    def test_execute_task_loads_files(self, mock_print, mock_file, mock_safe, mock_isfile, mock_exists, mock_post, mock_parse, mock_rmap, mock_gen):
        mock_rmap.generate_repo_map.return_value = "class Foo: ..."
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "your_project/main.py"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp
        ai_pipeline.execute_task("Update main module")

    @patch('scripts.ai_pipeline.ai_generate', return_value="just text no files")
    @patch('scripts.ai_pipeline.repo_map')
    @patch('scripts.ai_pipeline.parse_and_write_files', return_value=0)
    @patch('requests.post', side_effect=Exception("timeout"))
    @patch('builtins.print')
    def test_execute_task_discovery_fails(self, mock_print, mock_post, mock_parse, mock_rmap, mock_gen):
        mock_rmap.generate_repo_map.return_value = "empty"
        ai_pipeline.execute_task("Do something")


class TestSaveRollbackEdgeCases(unittest.TestCase):
    """Edge cases for rollback."""

    def test_save_rollback_failure(self):
        with patch('scripts.ai_pipeline.git_run', side_effect=Exception("not a repo")):
            result = ai_pipeline.save_rollback_point()
            self.assertIsNone(result)

    def test_rollback_none_hash(self):
        with patch('scripts.ai_pipeline.git_run') as mock_git:
            ai_pipeline.rollback_if_worse(None, False)
            mock_git.assert_not_called()

    def test_rollback_fail(self):
        with patch('scripts.ai_pipeline.git_run', side_effect=Exception("reset failed")):
            with patch('builtins.print'):
                ai_pipeline.rollback_if_worse("abc", False)


class TestPushWithChanges(unittest.TestCase):
    """Additional push tests."""

    @patch('scripts.ai_pipeline.TARGET_REPO', 'test/repo')
    @patch('scripts.ai_pipeline.TARGET_REPO_TOKEN', 'token')
    @patch('scripts.ai_pipeline.git_run', side_effect=Exception("push failed"))
    @patch('builtins.print')
    def test_push_exception(self, mock_print, mock_git):
        ai_pipeline.push_to_target_repository()
        # Should print error but not crash


if __name__ == '__main__':
    unittest.main()

