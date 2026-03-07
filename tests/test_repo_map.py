import sys
import os
import unittest
from unittest.mock import patch, mock_open

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import scripts.repo_map as repo_map

class TestRepoMap(unittest.TestCase):
    def test_generate_python_map_success(self):
        mock_code = "def my_func():\n    '''docstring'''\n    pass\n\nclass MyClass:\n    def method(self):\n        pass"
        with patch('builtins.open', mock_open(read_data=mock_code)):
            res = repo_map._generate_python_map("test.py")
            self.assertIn("def my_func():", res)
            self.assertIn("'''docstring'''", res)
            self.assertIn("class MyClass:", res)
            self.assertIn("def method(self):", res)

    def test_generate_python_map_syntax_error(self):
        mock_code = "def my_func(:"
        with patch('builtins.open', mock_open(read_data=mock_code)):
            res = repo_map._generate_python_map("test.py")
            self.assertEqual(res, "SyntaxError parsing test.py")

    def test_generate_python_map_read_error(self):
        with patch('builtins.open', side_effect=Exception("Read Error")):
            res = repo_map._generate_python_map("test.py")
            self.assertIn("Could not read test.py", res)

    def test_generate_python_map_empty_ast(self):
        mock_code = "x = 10\ny = 20"
        with patch('builtins.open', mock_open(read_data=mock_code)):
            res = repo_map._generate_python_map("test.py")
            self.assertEqual(res, "")

    @patch('os.path.exists', return_value=False)
    def test_generate_repo_map_no_dir(self, mock_exists):
        self.assertEqual(repo_map.generate_repo_map("non_existent"), "Project directory is empty or does not exist.")

    @patch('os.path.exists', return_value=True)
    @patch('os.walk')
    @patch('scripts.repo_map._generate_python_map')
    def test_generate_repo_map_with_files(self, mock_gen_py, mock_walk, mock_exists):
        mock_walk.return_value = [
            ('your_project', (), ('main.py', 'style.css', 'hidden.txt')),
            ('your_project/.git', (), ('config',)),
        ]
        mock_gen_py.return_value = "def test():\n    pass"
        
        res = repo_map.generate_repo_map("your_project")
        
        self.assertIn("--- FILE: your_project\\main.py ---", res.replace("/", "\\"))
        self.assertIn("def test():", res)
        self.assertIn("--- FILE: your_project\\style.css ---", res.replace("/", "\\"))
        self.assertIn("Non-python file", res)
        self.assertNotIn("hidden.txt", res)
        self.assertNotIn(".git", res)

    @patch('os.path.exists', return_value=True)
    @patch('os.walk', return_value=[('your_project', (), ('image.png',))])
    def test_generate_repo_map_unsupported_files(self, mock_walk, mock_exists):
        self.assertEqual(repo_map.generate_repo_map("your_project"), "No supported code files found.")

if __name__ == '__main__':
    unittest.main()
