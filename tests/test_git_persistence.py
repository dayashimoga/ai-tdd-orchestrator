import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add repo root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import scripts.git_persistence as git_persistence

class TestGitPersistence(unittest.TestCase):

    @patch('subprocess.run')
    def test_run_git_command_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="everything up-to-date", stderr="", returncode=0)
        res = git_persistence.run_git_command(["push"])
        self.assertEqual(res, "everything up-to-date")

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_init_repository_new(self, mock_exists, mock_run):
        mock_exists.return_value = False # .git does not exist
        git_persistence.init_repository("dummy_path", "https://github.com/test/repo.git", "token")
        
        # Should call git init and git remote add
        self.assertTrue(mock_run.called)
        # Check that 'init' was called
        args_list = [call.args[0] for call in mock_run.call_args_list]
        self.assertIn(['git', 'init'], args_list)
        self.assertIn(['git', 'remote', 'add', 'origin', 'https://token@github.com/test/repo.git'], args_list)

    @patch('subprocess.run')
    def test_persist_changes_no_changes(self, mock_run):
        # Mock outputs for: config(name) check, config(email) check, add, status(empty)
        # By returning non-empty stdout for config, we avoid the 'set' calls
        mock_run.side_effect = [
            MagicMock(stdout="AI Orchestrator", returncode=0), # name check
            MagicMock(stdout="orchestrator@ai.local", returncode=0), # email check
            MagicMock(stdout="", returncode=0), # add
            MagicMock(stdout="", returncode=0), # status (empty)
        ]
        
        with patch('builtins.print'):
            git_persistence.persist_changes("dummy_path")
        
        # Should not call git commit or git push
        args_list = [call.args[0] for call in mock_run.call_args_list]
        # Any call with 'commit' should NOT be in the list
        for args in args_list:
            self.assertNotIn('commit', args)
        for args in args_list:
            self.assertNotIn('push', args)

    @patch('subprocess.run')
    def test_persist_changes_with_push(self, mock_run):
        # Mock outputs for: config name check (empty), config name set, config email check (empty), config email set, 
        # add(0), status(M file), commit(0), remote(origin), rev-parse(main), push(0)
        mock_run.side_effect = [
            MagicMock(stdout="", returncode=0), # name check -> empty
            MagicMock(stdout="", returncode=0), # name set
            MagicMock(stdout="", returncode=0), # email check -> empty
            MagicMock(stdout="", returncode=0), # email set
            MagicMock(stdout="", returncode=0), # add
            MagicMock(stdout="M file.py", returncode=0), # status
            MagicMock(stdout="", returncode=0), # commit
            MagicMock(stdout="origin", returncode=0), # remote
            MagicMock(stdout="main", returncode=0), # rev-parse
            MagicMock(stdout="", returncode=0), # push
        ]
        
        git_persistence.persist_changes("dummy_path")
        
        args_list = [call.args[0] for call in mock_run.call_args_list]
        self.assertIn(['git', 'add', '.'], args_list)
        self.assertIn(['git', 'commit', '-m', "AI Orchestrator: Update generated code"], args_list)
        self.assertIn(['git', 'push', '-u', 'origin', 'main'], args_list)

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_ensure_state_continuity_clone(self, mock_exists, mock_run):
        # Case: Repo exists on GitHub, path doesn't exist -> clone
        mock_exists.return_value = False
        with patch('scripts.git_persistence._check_repo_exists_github', return_value=True):
            git_persistence.ensure_state_continuity("dummy_path", "https://github.com/test/repo.git", "token")
            # Clone happens without cwd
            mock_run.assert_called_with(['git', 'clone', "https://token@github.com/test/repo.git", "dummy_path"], check=True)

    @patch('scripts.git_persistence.requests.get')
    def test_check_repo_exists_github(self, mock_get):
        # Case 1: Success
        mock_get.return_value.status_code = 200
        res = git_persistence._check_repo_exists_github("https://github.com/user/repo", "token123")
        self.assertTrue(res)
        
        # Case 2: Not Found
        mock_get.return_value.status_code = 404
        res = git_persistence._check_repo_exists_github("https://github.com/user/repo", "token123")
        self.assertFalse(res)

    def test_inject_pat_into_url(self):
        url = "https://github.com/user/repo"
        token = "ghp_123"
        authed = git_persistence._inject_pat_into_url(url, token)
        self.assertEqual(authed, "https://ghp_123@github.com/user/repo")

    @patch('scripts.git_persistence._check_repo_exists_github')
    @patch('scripts.git_persistence.init_repository')
    @patch('os.path.exists')
    @patch('os.makedirs')
    def test_ensure_state_continuity_new_local(self, mock_mkdir, mock_exists, mock_init, mock_check):
        # Path doesn't exist, and repo doesn't exist on GitHub -> init local
        mock_exists.return_value = False
        mock_check.return_value = False
        
        git_persistence.ensure_state_continuity("dummy_path", "https://github.com/user/repo", "token")
        
        mock_mkdir.assert_called_with("dummy_path", exist_ok=True)
        mock_init.assert_called_with("dummy_path", "https://github.com/user/repo", "token")

if __name__ == "__main__":
    unittest.main()
