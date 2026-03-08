import sys
import os
import unittest
from unittest.mock import patch, mock_open, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import scripts.repo_map as repo_map

class TestRepoMap(unittest.TestCase):
    def setUp(self):
        super().setUp()
        repo_map._AST_CACHE.clear()

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
        
        self.assertIn("def test():", res)
        self.assertNotIn(".git", res)

    @patch('os.path.exists', return_value=True)
    @patch('os.walk', return_value=[('your_project', (), ('image.png',))])
    def test_generate_repo_map_unsupported_files(self, mock_walk, mock_exists):
        self.assertEqual(repo_map.generate_repo_map("your_project"), "No supported code files found.")

    def test_parse_file_python(self):
        """O3: Test _parse_file for Python files."""
        with patch('scripts.repo_map._generate_python_map', return_value="def foo():"):
            result = repo_map._parse_file(
                "test.py", "test.py", "test.py",
                (".py",), (".js",), (".css",)
            )
            self.assertIsNotNone(result)
            self.assertIn("FILE", result[0])
            self.assertEqual(result[1], "def foo():")

    def test_parse_file_python_empty(self):
        """O3: Test _parse_file for Python files with no structural elements."""
        with patch('scripts.repo_map._generate_python_map', return_value=""):
            result = repo_map._parse_file(
                "test.py", "test.py", "test.py",
                (".py",), (".js",), (".css",)
            )
            self.assertEqual(result[1], "# No classes or functions defined.")

    def test_parse_file_js(self):
        """O3: Test _parse_file for JS files."""
        with patch('scripts.repo_map._generate_js_ts_map', return_value="function foo()"):
            result = repo_map._parse_file(
                "app.js", "app.js", "app.js",
                (".py",), (".js",), (".css",)
            )
            self.assertIsNotNone(result)
            self.assertEqual(result[1], "function foo()")

    def test_parse_file_js_empty(self):
        """O3: Test _parse_file for JS files with no functions."""
        with patch('scripts.repo_map._generate_js_ts_map', return_value=""):
            result = repo_map._parse_file(
                "app.js", "app.js", "app.js",
                (".py",), (".js",), (".css",)
            )
            self.assertEqual(result[1], "# No functions or classes found.")

    def test_parse_file_other(self):
        """O3: Test _parse_file for other supported files."""
        result = repo_map._parse_file(
            "style.css", "style.css", "style.css",
            (".py",), (".js",), (".css",)
        )
        self.assertIsNotNone(result)
        self.assertIn("Non-python", result[1])

    def test_parse_file_unsupported(self):
        """O3: Test _parse_file returns None for unsupported files."""
        result = repo_map._parse_file(
            "image.png", "image.png", "image.png",
            (".py",), (".js",), (".css",)
        )
        self.assertIsNone(result)

    def test_js_ts_map_read_error(self):
        with patch('builtins.open', side_effect=Exception("Read Error")):
            res = repo_map._generate_js_ts_map("test.js")
            self.assertIn("Could not read test.js", res)

    def test_js_ts_map_function(self):
        js_code = "function myFunc(a, b) { return a + b; }"
        with patch('builtins.open', mock_open(read_data=js_code)):
            res = repo_map._generate_js_ts_map("test.js")
            self.assertIn("function myFunc(a, b)", res)

    def test_js_ts_map_arrow_function(self):
        js_code = "const myFunc = (a, b) => { return a + b; }"
        with patch('builtins.open', mock_open(read_data=js_code)):
            res = repo_map._generate_js_ts_map("test.js")
            self.assertIn("const myFunc = (a, b) =>", res)

    def test_js_ts_map_class(self):
        js_code = "class MyClass extends Base {\n  constructor() {\n  }\n}"
        with patch('builtins.open', mock_open(read_data=js_code)):
            res = repo_map._generate_js_ts_map("test.js")
            self.assertIn("class MyClass(Base)", res)

    def test_js_ts_map_empty(self):
        js_code = "// just a comment"
        with patch('builtins.open', mock_open(read_data=js_code)):
            res = repo_map._generate_js_ts_map("test.js")
            self.assertEqual(res, "")

    @patch('os.path.exists', return_value=True)
    @patch('os.walk')
    @patch('scripts.repo_map._parse_file')
    def test_generate_repo_map_parallel(self, mock_parse, mock_walk, mock_exists):
        """O3: Test parallel file parsing threshold."""
        # Generate enough files to trigger parallel parsing
        files = tuple(f"file{i}.py" for i in range(12))
        mock_walk.return_value = [('project', (), files)]
        mock_parse.return_value = ("--- FILE: f ---", "def x():")
        
        result = repo_map.generate_repo_map("project")
        self.assertIn("def x():", result)


if __name__ == '__main__':
    unittest.main()
