import sys
import os
import subprocess
import unittest
import io
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

    def test_extract_test_failures(self):
        err_out = (
            "=================== FAILURES ===================\n"
            "___ test_foo ____\n"
            ">       assert 1 == 2\n"
            "E       AssertionError: assert 1 == 2\n"
            "== short test summary info ==\n"
            "FAILED tests/test_foo.py::test_foo - AssertionError"
        )
        res = ai_pipeline.extract_test_failures(err_out)
        self.assertIn("AssertionError", res)
        self.assertIn("FAILED", res)

    def test_extract_test_failures_fallback(self):
        res = ai_pipeline.extract_test_failures("just random text with no failures")
        self.assertEqual(res.strip(), "just random text with no failures")

    def test_validate_python_syntax(self):
        valid, err = ai_pipeline.validate_python_syntax("def foo():\n    pass\n", "test.py")
        self.assertTrue(valid)

        invalid, err2 = ai_pipeline.validate_python_syntax("def foo()\n    pass", "test.py")
        self.assertFalse(invalid)
        self.assertIn("SyntaxError", err2)

        valid3, _ = ai_pipeline.validate_python_syntax("not python", "test.txt")
        self.assertTrue(valid3)

    def test_extract_test_failures_extended(self):
        # Line 131: ImportError test
        err_out = "ImportError: No module named 'fake'"
        res = ai_pipeline.extract_test_failures(err_out)
        self.assertIn("ImportError", res)

        # Line 139: in_failure = False
        err_out2 = (
            "== short test summary info ==\n"
            "FAILED tests/test_foo.py::test_foo\n"
            "\n"
            "This line is after the block\n"
        )
        res2 = ai_pipeline.extract_test_failures(err_out2)
        self.assertIn("FAILED", res2)
        self.assertNotIn("after the block", res2)

    def test_validate_llm_response_no_code(self):
        # Line 173: length > 50 and no ticks
        long_text = "This is a very long text that does not contain any code blocks or any file delimiters and should be rejected."
        valid, err = ai_pipeline.validate_llm_response(long_text)
        self.assertFalse(valid)
        self.assertIn("no code blocks", err)

    def test_parse_and_write_files_syntax_error(self):
        # CG6: Syntax-invalid Python files are now REFUSED (not written)
        raw = "--- FILE: bad.py ---\ndef foo("
        with patch('scripts.ai_pipeline.safe_path', return_value="your_project/bad.py"):
            with patch('os.makedirs'):
                with patch('builtins.open', mock_open()):
                    with patch('builtins.print') as mock_print:
                        with patch('scripts.ai_pipeline.validate_python_syntax', return_value=(False, "SyntaxError in bad.py: stable error")):
                            count = ai_pipeline.parse_and_write_files(raw, "your_project")
                            self.assertEqual(count, 0)  # CG6: file NOT written
                            mock_print.assert_any_call("❌ REJECTED bad.py: SyntaxError in bad.py: stable error — file NOT written (prevents snapshot pollution)")
                            mock_print.assert_any_call("\n⚠️ 1 Python file(s) REJECTED due to syntax errors")

    def test_extract_failures_full_short_summary(self):
        # Cover lines 131, 134-140
        err_out = "ImportError: fake\n== short test summary info ==\nFAILED test.py\nERROR test2.py\n\nignored"
        res = ai_pipeline.extract_test_failures(err_out)
        self.assertIn("ImportError", res)
        self.assertIn("FAILED test.py", res)
        self.assertIn("ERROR test2.py", res)

    def test_validate_syntax_explicit(self):
        # Cover lines 152-153
        valid, err = ai_pipeline.validate_python_syntax("x = 1\n", "script.py")
        self.assertTrue(valid)

    def test_parse_and_write_files_odd_parts(self):

        # Line 192: i + 1 >= len(parts)
        raw = "--- FILE: file.py ---"
        count = ai_pipeline.parse_and_write_files(raw)
        self.assertEqual(count, 0)


    def test_gpu_cost_err(self):
        with patch('scripts.gpu_platform.get_platform_info', side_effect=Exception("api down")):
            res = ai_pipeline.estimate_gpu_cost(100)
            self.assertEqual(res, "Unknown")

    def test_update_task_plan_no_file(self):
        with patch('os.makedirs'):
            with patch('os.path.exists', return_value=False):
                with patch('builtins.open', mock_open()):
                    with patch('builtins.print') as mock_print:
                        ai_pipeline.update_task_plan("task")
                        mock_print.assert_any_call("⚠️ No tasks.md found to update.")


class TestDetectTestCommand(unittest.TestCase):

    @patch('os.walk')
    def test_detect_pytest(self, mock_walk):
        mock_walk.return_value = [("project", [], ["main.py"])]
        cmd = ai_pipeline.detect_test_command("project")
        # cmd is a list, e.g. [sys.executable, "-m", "pytest", ...]
        self.assertIn("pytest", str(cmd))

    @patch('os.walk')
    @patch('os.path.exists')
    def test_detect_npm(self, mock_exists, mock_walk):
        mock_walk.return_value = [("project", [], ["file.txt"])]
        mock_exists.side_effect = lambda p: p.endswith('package.json')
        # We need to mock open for package.json
        import json
        pkg_data = json.dumps({"test": "echo 'ok'"})
        with patch('builtins.open', mock_open(read_data=pkg_data)):
            cmd = ai_pipeline.detect_test_command("project")
            self.assertIn("npm", cmd[0])

    @patch('os.walk')
    def test_detect_go(self, mock_walk):
        mock_walk.return_value = [("project", [], ["main.go"])]
        cmd = ai_pipeline.detect_test_command("project")
        self.assertEqual(cmd[0], "go")

    @patch('os.walk')
    @patch('os.path.exists')
    def test_detect_fallback(self, mock_exists, mock_walk):
        mock_walk.return_value = [("project", [], [])]
        mock_exists.return_value = False
        cmd = ai_pipeline.detect_test_command("project")
        self.assertIn("pytest", str(cmd))





class TestAIGenerate(unittest.TestCase):

    """Tests for LLM API interaction."""

    @patch('scripts.llm_router._retry_request')
    def test_ai_generate_success(self, mock_retry):
        import json
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = [
            json.dumps({"response": "hello "}).encode(),
            json.dumps({"response": "world"}).encode(),
        ]
        mock_response.raise_for_status = MagicMock()
        mock_retry.return_value = mock_response
        result = ai_pipeline.ai_generate("test prompt")
        self.assertEqual(result, "hello world")

    @patch('scripts.llm_router._retry_request', side_effect=Exception("Connection refused"))
    def test_ai_generate_failure(self, mock_retry):
        result = ai_pipeline.ai_generate("test prompt")
        self.assertEqual(result, "")


class TestRepositoryManagement(unittest.TestCase):
    """Tests for setup_target_repository and push_to_target_repository."""

    @patch('scripts.ai_pipeline.TARGET_REPO', 'test/repo')
    @patch('scripts.ai_pipeline.PROJECT_TYPE', 'new')
    @patch('scripts.ai_pipeline.TARGET_REPO_TOKEN', 'token')
    @patch('scripts.ai_pipeline.get_github_client')
    def test_setup_repo_exists_fallback(self, mock_gh_client):
        # Mocking the 422 "already exists" error
        mock_user = MagicMock()
        mock_user.login = "testuser"
        # First call fails, second call (recursive) should avoid the loop
        mock_user.create_repo.side_effect = [Exception("422: name already exists on this account"), MagicMock()]
        mock_gh = MagicMock()
        mock_gh.get_user.return_value = mock_user
        mock_gh_client.return_value = mock_gh
        
        # We need to stop the recursion after the first retry
        with patch('scripts.ai_pipeline.git_run'):
            ai_pipeline.setup_target_repository()
            self.assertTrue(mock_user.create_repo.called)

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
    @patch('os.makedirs')
    @patch('builtins.open', new_callable=mock_open)
    @patch('builtins.print')
    def test_generate_task_plan(self, mock_print, mock_file, mock_makedirs, mock_gen):
        ai_pipeline.generate_task_plan("Build a calculator")
        mock_gen.assert_called_once()
        
    @patch('scripts.ai_pipeline.ai_generate', return_value="- [ ] Task 1\n- [ ] New Task")
    @patch('os.makedirs')
    @patch('os.path.exists', side_effect=[True, True, True])
    @patch('builtins.open', new_callable=mock_open, read_data="- [ ] Task 1\n")
    @patch('builtins.print')
    def test_update_task_plan_existing(self, mock_print, mock_file, mock_exists, mock_makedirs, mock_gen):
        ai_pipeline.update_task_plan("Add a new feature")
        mock_gen.assert_called_once()
        
    @patch('scripts.ai_pipeline.ai_generate', return_value="- [ ] Task 1\n- [ ] New Task")
    @patch('os.makedirs')
    @patch('os.path.exists', side_effect=[False, True, True])
    @patch('builtins.open', new_callable=mock_open, read_data="- [ ] Task 1\n")
    @patch('builtins.print')
    def test_update_task_plan_new_req(self, mock_print, mock_file, mock_exists, mock_makedirs, mock_gen):
        ai_pipeline.update_task_plan("Add a new feature")
        mock_gen.assert_called_once()

    @patch('scripts.ai_pipeline.ai_generate', return_value="--- FILE: main.py ---\nprint('hi')")
    @patch('scripts.ai_pipeline.repo_map')
    @patch('scripts.ai_pipeline.parse_and_write_files', return_value=1)
    @patch('scripts.llm_router.generate', return_value="NONE")
    @patch('builtins.print')
    def test_execute_task(self, mock_print, mock_llm, mock_parse, mock_rmap, mock_gen):
        mock_rmap.generate_repo_map.return_value = "class Foo: ..."
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
            # We need to simulate the sequence of git commands: add, status, commit, rev-parse
            mock_status = MagicMock()
            mock_status.stdout = " M file.py"
            mock_git.side_effect = [
                MagicMock(),            # git add .
                mock_status,            # git status --porcelain
                MagicMock(),            # git commit -m ...
                MagicMock(stdout="abc123def") # git rev-parse HEAD
            ]
            result = ai_pipeline.save_rollback_point()
            self.assertEqual(result, "abc123def")
            self.assertEqual(mock_git.call_count, 4)

    def test_rollback_if_worse(self):
        with patch('scripts.ai_pipeline.git_run') as mock_git:
            with patch('builtins.print'):
                ai_pipeline.rollback_if_worse("abc123", False)
                # It should call reset --hard and clean -fd
                self.assertEqual(mock_git.call_count, 2)

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
    @patch('scripts.ai_pipeline.update_task_plan')
    @patch('scripts.ai_pipeline.run_tdd_loop')
    @patch('scripts.ai_pipeline.push_to_target_repository')
    @patch('os.path.exists', side_effect=[True, False, False, False, False, False]) # prompt.txt exists, project_tasks.md does not
    @patch('builtins.open', new_callable=mock_open, read_data="Build app")
    def test_main_manual_new(self, mock_file, mock_exists, mock_push, mock_tdd, mock_update, mock_plan, mock_ensure, mock_setup):
        ai_pipeline.main()
        mock_setup.assert_called_once()
        mock_ensure.assert_called_once()
        mock_plan.assert_called_once()
        mock_tdd.assert_called_once()
        mock_push.assert_called_once()

    @patch('sys.argv', ['ai_pipeline.py', '--manual'])
    @patch('scripts.ai_pipeline.setup_target_repository')
    @patch('scripts.ai_pipeline.ensure_code_exists')
    @patch('scripts.ai_pipeline.generate_task_plan')
    @patch('scripts.ai_pipeline.update_task_plan')
    @patch('scripts.ai_pipeline.run_tdd_loop')
    @patch('scripts.ai_pipeline.push_to_target_repository')
    @patch('os.path.exists', side_effect=[True, True, True, True, True, True]) # prompt.txt exists, project_tasks.md exists
    @patch('builtins.open', new_callable=mock_open, read_data="Build app")
    def test_main_manual_existing(self, mock_file, mock_exists, mock_push, mock_tdd, mock_update, mock_plan, mock_ensure, mock_setup):
        ai_pipeline.main()
        mock_setup.assert_called_once()
        mock_update.assert_called_once()
        mock_tdd.assert_called_once()
        mock_push.assert_called_once()

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


class TestWebhookAndMisc(unittest.TestCase):
    """Tests for webhooks and cost estimation."""

    @patch('os.getenv', return_value="https://webhook.test")
    @patch('requests.post')
    def test_send_webhook_success(self, mock_post, mock_env):
        ai_pipeline.send_webhook_notification("test msg")
        mock_post.assert_called_once()
        self.assertIn("test msg", mock_post.call_args[1]['json']['content'])

    @patch('os.getenv', return_value="")
    @patch('requests.post')
    def test_send_webhook_disabled(self, mock_post, mock_env):
        ai_pipeline.send_webhook_notification("test msg")
        mock_post.assert_not_called()

    @patch('os.getenv', return_value="https://webhook.test")
    @patch('requests.post', side_effect=Exception("timeout"))
    @patch('builtins.print')
    def test_send_webhook_error(self, mock_print, mock_post, mock_env):
        ai_pipeline.send_webhook_notification("test msg")
        mock_print.assert_called_with("⚠️ Webhook notification failed: timeout")

    @patch('scripts.gpu_platform.get_platform_info', return_value={"cost": "$0.50/hr"})
    @patch('scripts.gpu_platform.select_platform', return_value=("runpod", "url"))
    def test_estimate_gpu_cost(self, mock_sel, mock_info):
        # 3600 seconds = 1 hour -> $0.50
        cost = ai_pipeline.estimate_gpu_cost(3600)
        self.assertIn("~$0.5000", cost)

    @patch('scripts.gpu_platform.get_platform_info', return_value={"free": True})
    @patch('scripts.gpu_platform.select_platform', return_value=("local", "url"))
    def test_estimate_gpu_cost_free(self, mock_sel, mock_info):
        cost = ai_pipeline.estimate_gpu_cost(100)
        self.assertEqual(cost, "Free")

    @patch('scripts.gpu_platform.select_platform', return_value=("local", "http://test"))
    def test_lazy_platform_url(self, mock_sel):
        # Reset globals for testing
        ai_pipeline._detected_platform = None
        ai_pipeline._detected_url = None
        url = ai_pipeline._get_platform_url()
        self.assertEqual(url, "http://test")
        mock_sel.assert_called_once()
        # Second call should use cached global and not call select_platform again
        url2 = ai_pipeline._get_platform_url()
        self.assertEqual(url2, "http://test")
        self.assertEqual(mock_sel.call_count, 1)


class TestUpdateTaskPlanRequirements(unittest.TestCase):
    """Tests for the new deduplicating requirements behavior in update_task_plan."""

    @patch('scripts.ai_pipeline.ai_generate', return_value="- [ ] Task\n")
    @patch('os.makedirs')
    @patch('os.path.exists', side_effect=lambda p: True)  # Both reqs and tasks exist
    def test_update_task_plan_duplicate_reqs(self, mock_exists, mock_makedirs, mock_ai):
        # Setup mock open
        mock_file_obj = mock_open(read_data="Old reqs\n## New Requirements (Update)\nExisting prompt\n")
        
        with patch('builtins.open', mock_file_obj) as mock_file:
            ai_pipeline.update_task_plan("Existing prompt")
            
            # Should have called ai_generate
            self.assertTrue(mock_ai.called)
            
            # Should NOT have appended to requirements.md
            write_calls = mock_file().write.call_args_list
            failed_to_dedupe = any("Existing prompt" in str(args) for args, kwargs in write_calls)
            self.assertFalse(failed_to_dedupe)

    @patch('scripts.ai_pipeline.ai_generate', return_value="- [ ] Task\n")
    @patch('os.makedirs')
    @patch('os.path.exists', side_effect=lambda p: True) 
    def test_update_task_plan_new_reqs(self, mock_exists, mock_makedirs, mock_ai):
        mock_file_obj = mock_open(read_data="Old reqs\n")
        
        with patch('builtins.open', mock_file_obj) as mock_file:
            ai_pipeline.update_task_plan("New awesome prompt")
            
            self.assertTrue(mock_ai.called)
            
            # Should HAVE appended to requirements.md
            write_calls = mock_file().write.call_args_list
            success = any("New awesome prompt" in str(args) for args, kwargs in write_calls)
            self.assertTrue(success)


class TestTDDLoopBranches(unittest.TestCase):
    """Tests for run_tdd_loop branch coverage."""

    @patch('os.path.exists', return_value=False)
    @patch('builtins.print')
    def test_tdd_loop_no_tasks_file(self, mock_print, mock_exists):
        ai_pipeline.run_tdd_loop(max_iterations=1)

    @patch('os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data="- [x] Done task\n")
    @patch('subprocess.run')
    @patch('os.makedirs')
    @patch('builtins.print')
    def test_tdd_loop_all_done(self, mock_print, mock_makedirs, mock_subrun, mock_file, mock_exists):
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
    @patch('scripts.llm_router.generate', return_value="your_project/main.py")
    @patch('os.path.exists', return_value=True)
    @patch('os.path.isfile', return_value=True)
    @patch('scripts.ai_pipeline.safe_path', return_value="your_project/main.py")
    @patch('builtins.open', new_callable=mock_open, read_data="content")
    @patch('builtins.print')
    def test_execute_task_loads_files(self, mock_print, mock_file, mock_safe, mock_isfile, mock_exists, mock_llm, mock_parse, mock_rmap, mock_gen):
        mock_rmap.generate_repo_map.return_value = "class Foo: ..."
        ai_pipeline.execute_task("Update main module")

    @patch('scripts.ai_pipeline.ai_generate', return_value="just text no files")
    @patch('scripts.ai_pipeline.repo_map')
    @patch('scripts.ai_pipeline.parse_and_write_files', return_value=0)
    @patch('scripts.llm_router.generate', side_effect=Exception("timeout"))
    @patch('builtins.print')
    def test_execute_task_discovery_fails(self, mock_print, mock_llm, mock_parse, mock_rmap, mock_gen):
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


class TestCompiledRegexPatterns(unittest.TestCase):
    """Tests for compiled regex patterns (O4)."""

    def test_re_ansi_escape(self):
        text = "\x1b[31mERROR\x1b[0m: something"
        result = ai_pipeline._RE_ANSI_ESCAPE.sub('', text)
        self.assertIn("ERROR", result)
        self.assertNotIn("\x1b", result)

    def test_re_file_delimiter(self):
        text = "--- FILE: main.py ---\ncode here"
        matches = ai_pipeline._RE_FILE_DELIMITER.findall(text)
        self.assertEqual(matches, ["main.py"])

    def test_re_code_block(self):
        text = "```python\ndef foo():\n    pass\n```"
        match = ai_pipeline._RE_CODE_BLOCK.search(text)
        self.assertIsNotNone(match)
        self.assertIn("def foo():", match.group(1))

    def test_re_error_types(self):
        self.assertIsNotNone(ai_pipeline._RE_ERROR_TYPES.search("ImportError: no module"))
        self.assertIsNotNone(ai_pipeline._RE_ERROR_TYPES.search("SyntaxError: bad"))
        self.assertIsNone(ai_pipeline._RE_ERROR_TYPES.search("all tests passed"))


class TestAIGenerateWithRouter(unittest.TestCase):
    """Tests for ai_generate using llm_router."""

    @patch('scripts.llm_router._retry_request')
    def test_ai_generate_success(self, mock_retry):
        import json
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = [
            json.dumps({"response": "hello "}).encode(),
            json.dumps({"response": "world"}).encode(),
        ]
        mock_response.raise_for_status = MagicMock()
        mock_retry.return_value = mock_response
        result = ai_pipeline.ai_generate("test prompt")
        self.assertEqual(result, "hello world")

    @patch('scripts.llm_router._retry_request', side_effect=Exception("Connection refused"))
    def test_ai_generate_failure(self, mock_retry):
        result = ai_pipeline.ai_generate("test prompt")
        self.assertEqual(result, "")


class TestInstallProjectDependencies(unittest.TestCase):
    """Tests for the _install_project_dependencies function."""

    def setUp(self):
        ai_pipeline._deps_installed_hash = ""

    @patch('os.path.exists', return_value=False)
    def test_no_requirements_file(self, mock_exists):
        ai_pipeline._install_project_dependencies("your_project")
        # Should print info message and not crash

    @patch('subprocess.run')
    @patch('builtins.open', mock_open(read_data="flask>=3.0\npytest>=8.0\n"))
    @patch('os.path.exists', return_value=True)
    def test_install_success(self, mock_exists, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        ai_pipeline._deps_installed_hash = ""
        ai_pipeline._install_project_dependencies("your_project")
        mock_run.assert_called_once()

    @patch('subprocess.run')
    @patch('builtins.open', mock_open(read_data="flask>=3.0\npytest>=8.0\n"))
    @patch('os.path.exists', return_value=True)
    def test_install_caches_hash(self, mock_exists, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        ai_pipeline._deps_installed_hash = ""
        ai_pipeline._install_project_dependencies("your_project")
        first_hash = ai_pipeline._deps_installed_hash
        self.assertNotEqual(first_hash, "")
        # Second call should skip (cached)
        mock_run.reset_mock()
        ai_pipeline._install_project_dependencies("your_project")
        mock_run.assert_not_called()

    @patch('subprocess.run')
    @patch('builtins.open', mock_open(read_data="flask>=3.0\n"))
    @patch('os.path.exists', return_value=True)
    def test_install_failure(self, mock_exists, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="ERROR: bad package")
        ai_pipeline._deps_installed_hash = ""
        ai_pipeline._install_project_dependencies("your_project")
        # Hash should NOT be cached on failure
        self.assertEqual(ai_pipeline._deps_installed_hash, "")

    @patch('subprocess.run', side_effect=Exception("pip exploded"))
    @patch('builtins.open', mock_open(read_data="flask\n"))
    @patch('os.path.exists', return_value=True)
    def test_install_exception(self, mock_exists, mock_run):
        ai_pipeline._deps_installed_hash = ""
        ai_pipeline._install_project_dependencies("your_project")
        # Should not crash


class TestTDDLoopEarlyAbort(unittest.TestCase):
    """Test the early abort mechanism when LLM repeatedly fails."""

    @patch("scripts.ai_pipeline.execute_task")
    @patch("scripts.ai_pipeline.run_pytest_validation")
    @patch("scripts.ai_pipeline.save_rollback_point")
    @patch("scripts.ai_pipeline.rollback_if_worse")
    @patch("scripts.ai_pipeline.post_help_comment")
    @patch("scripts.ai_pipeline.generate_run_summary")
    def test_tdd_loop_early_abort(self, mock_summary, mock_post_help, mock_rollback, mock_save_rollback, mock_run_pytest, mock_execute_task):
        """Test that TDD loop aborts early if LLM fails to generate files 3 times consistently."""
        
        # Setup mock file system state for the task
        with patch('builtins.open', mock_open(read_data="- [ ] Task 1\n")) as m_open:
            with patch('os.path.exists') as m_exists:
                # Mock project_tasks.md exists, conftest.py does not
                m_exists.side_effect = lambda path: path == "your_project/project_tasks.md"
                
                # Mock execute_task to always return 0 files written
                mock_execute_task.return_value = 0
                
                # Capture stdout
                captured_output = io.StringIO()
                original_stdout = sys.stdout
                sys.stdout = captured_output

                try:
                    # Run the loop with max 15 iterations
                    ai_pipeline.run_tdd_loop(max_iterations=15)
                finally:
                    sys.stdout = original_stdout
                
                # Verify the loop ran `execute_task` exactly 3 times before breaking
                self.assertEqual(mock_execute_task.call_count, 3)
                
                # Verify it aborted early with the correct message
                output_str = captured_output.getvalue()
                self.assertIn("CRITICAL: LLM failed to generate valid code 3 times in a row", output_str)
                self.assertIn("aborted early after 3 iterations due to catastrophic LLM failure", output_str)
                
                # Verify help comment was posted
                mock_post_help.assert_called_once()
                
                # Ensure pytest validation was skipped entirely
                mock_run_pytest.assert_not_called()


class TestExtractModuleNotFound(unittest.TestCase):
    """Tests for ModuleNotFoundError detection in extract_test_failures."""

    def test_module_not_found_detected(self):
        feedback = (
            "ERRORS\n"
            "ImportError while importing test module\n"
            "E   ModuleNotFoundError: No module named 'flask'\n"
            "short test summary info\n"
            "ERROR your_project/tests/test_app.py\n"
        )
        result = ai_pipeline.extract_test_failures(feedback)
        self.assertIn("ModuleNotFoundError", result)
        self.assertIn("flask", result)
        self.assertIn("requirements.txt", result)

    def test_multiple_missing_modules(self):
        feedback = (
            "E   ModuleNotFoundError: No module named 'flask'\n"
            "E   ModuleNotFoundError: No module named 'sqlalchemy'\n"
        )
        result = ai_pipeline.extract_test_failures(feedback)
        self.assertIn("flask", result)
        self.assertIn("sqlalchemy", result)

    def test_no_module_error_not_triggered(self):
        feedback = "FAILED test_app.py::test_main - AssertionError: 1 != 2\n"
        result = ai_pipeline.extract_test_failures(feedback)
        self.assertNotIn("ModuleNotFoundError", result)


class TestExtractCoverageTable(unittest.TestCase):
    """Tests for coverage table extraction in extract_test_failures."""

    def test_coverage_table_parsed(self):
        feedback = (
            "FAIL Required test coverage of 90% not reached. Total coverage: 85%\n"
            "Name                       Stmts   Miss  Cover   Missing\n"
            "--------------------------------------------------------\n"
            "app.py                        50     10    80%   15-20, 45-50\n"
            "models.py                     30      5    83%   8-12\n"
            "TOTAL                         80     15    81%\n"
        )
        result = ai_pipeline.extract_test_failures(feedback)
        self.assertIn("app.py", result)
        self.assertIn("15-20", result)
        self.assertIn("models.py", result)
        self.assertIn("COVERAGE DROPPED BELOW 90%", result)


class TestGitRun(unittest.TestCase):
    """Tests for the git_run utility wrapper."""

    @patch('subprocess.run')
    def test_git_run_default_cwd(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        ai_pipeline.git_run(["git", "status"])
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        self.assertEqual(kwargs["cwd"], "your_project")

    @patch('subprocess.run')
    def test_git_run_custom_cwd(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        ai_pipeline.git_run(["git", "log"], cwd="/tmp")
        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs["cwd"], "/tmp")

    @patch('subprocess.run')
    def test_git_run_timeout_default(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        ai_pipeline.git_run(["git", "status"])
        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs["timeout"], ai_pipeline.GIT_TIMEOUT)


class TestSanitizeGeneratedCode(unittest.TestCase):
    """Tests for the _sanitize_generated_code function."""

    def test_strips_conversational_prose(self):
        code = (
            "def hello():\n"
            "    return 'world'\n"
            "This setup provides a basic structure for a project with tasks and a main entry point and tests\n"
        )
        result = ai_pipeline._sanitize_generated_code(code, "app.py")
        self.assertNotIn("This setup provides", result)
        self.assertIn("def hello():", result)

    def test_fixes_your_project_imports(self):
        code = "from your_project.app import app\nimport your_project.models\n"
        result = ai_pipeline._sanitize_generated_code(code, "tests/test_app.py")
        self.assertIn("from app import app", result)
        self.assertIn("import models", result)
        self.assertNotIn("your_project.", result)

    def test_preserves_comments(self):
        code = "# This is a really really long comment that describes what this module does in great detail for documentation\ndef foo():\n    pass\n"
        result = ai_pipeline._sanitize_generated_code(code, "app.py")
        self.assertIn("# This is a really", result)

    def test_preserves_short_lines(self):
        code = "x = 1\ny = 2\nresult = x + y\n"
        result = ai_pipeline._sanitize_generated_code(code, "app.py")
        self.assertEqual(result, code)

    def test_non_python_files_skip_prose_filter(self):
        code = "This is a description of the requirements for the project that should be included in the file\n"
        result = ai_pipeline._sanitize_generated_code(code, "requirements.txt")
        self.assertIn("This is a description", result)


class TestGetGithubClient(unittest.TestCase):
    """Cover get_github_client line 79."""

    @patch('scripts.ai_pipeline.Github')
    def test_get_github_client_with_token(self, mock_github):
        ai_pipeline.get_github_client("test_token")
        mock_github.assert_called_once_with("test_token")


class TestValidateLLMResponseEdge(unittest.TestCase):
    """Cover validate_llm_response edge cases."""

    def test_empty_response(self):
        valid, err = ai_pipeline.validate_llm_response("")
        self.assertFalse(valid)
        self.assertIn("empty", err.lower())

    def test_conversational_response(self):
        valid, err = ai_pipeline.validate_llm_response(
            "Sure! I'd be happy to help you build a REST API. Here is a simple flask application that manages tasks."
        )
        self.assertFalse(valid)
        self.assertIn("no code blocks", err.lower())


class TestRollbackDepCacheReset(unittest.TestCase):
    """Cover rollback_if_worse dep cache reset."""

    @patch('scripts.ai_pipeline.git_run')
    def test_rollback_resets_dep_cache(self, mock_git):
        ai_pipeline._deps_installed_hash = "abc123"
        ai_pipeline.rollback_if_worse("fake_hash", False)
        self.assertEqual(ai_pipeline._deps_installed_hash, "")

    def test_rollback_skip_on_success(self):
        ai_pipeline._deps_installed_hash = "abc123"
        ai_pipeline.rollback_if_worse("fake_hash", True)
        self.assertEqual(ai_pipeline._deps_installed_hash, "abc123")  # Not reset


class TestExecuteTaskReturn(unittest.TestCase):
    """Cover execute_task return value paths."""

    def test_dry_run_returns_zero(self):
        original = ai_pipeline.DRY_RUN
        ai_pipeline.DRY_RUN = True
        try:
            result = ai_pipeline.execute_task("test task")
            self.assertEqual(result, 0)
        finally:
            ai_pipeline.DRY_RUN = original


class TestParseWriteFilesReject(unittest.TestCase):
    """Cover CG6 reject path in parse_and_write_files."""

    def test_syntax_invalid_file_rejected(self):
        """Directly test that invalid Python is NOT written."""
        raw = "--- FILE: broken.py ---\ndef foo(\n--- FILE: good.txt ---\nhello world"
        with patch('scripts.ai_pipeline.safe_path', return_value="your_project/good.txt"):
            with patch('os.makedirs'):
                with patch('builtins.open', mock_open()):
                    count = ai_pipeline.parse_and_write_files(raw, "your_project")
                    # Only the .txt file should be written, not the broken .py
                    self.assertEqual(count, 1)

