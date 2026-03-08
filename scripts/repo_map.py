import os
import ast
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional
import json

# Minimal AST Cache: filepath -> {"mtime": float, "ast": str}
_AST_CACHE = {}
_CACHE_FILE = ".repo_map_cache.json"

def _load_cache():
    global _AST_CACHE
    if not _AST_CACHE and os.path.exists(_CACHE_FILE):
        try:
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                _AST_CACHE = json.load(f)
        except Exception:
            _AST_CACHE = {}

def _save_cache():
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_AST_CACHE, f)
    except Exception:
        pass


def _generate_python_map(file_path):
    """
    Parses a python file and returns a compressed structural outline
    containing only classes, function signatures, and their docstrings.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            file_content = f.read()
    except Exception as e:
        return f"Could not read {file_path}: {e}"

    try:
        tree = ast.parse(file_content)
    except SyntaxError:
        return f"SyntaxError parsing {file_path}"

    lines = []
    
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            sig = f"def {node.name}("
            args = [a.arg for a in node.args.args]
            sig += ", ".join(args) + "):"
            lines.append(sig)
            
            # Optionally grab docstring
            doc = ast.get_docstring(node)
            if doc:
                doc_preview = doc.split("\\n")[0][:60] + ("..." if len(doc) > 60 else "")
                lines.append(f"    '''{doc_preview}'''")
        
        elif isinstance(node, ast.ClassDef):
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            base_str = f"({', '.join(bases)})" if bases else ""
            lines.append(f"class {node.name}{base_str}:")
            
            doc = ast.get_docstring(node)
            if doc:
                doc_preview = doc.split("\\n")[0][:60] + ("..." if len(doc) > 60 else "")
                lines.append(f"    '''{doc_preview}'''")
                
            # Class methods
            for sub_node in node.body:
                if isinstance(sub_node, ast.FunctionDef) or isinstance(sub_node, ast.AsyncFunctionDef):
                    sig = f"    def {sub_node.name}("
                    args = [a.arg for a in sub_node.args.args]
                    sig += ", ".join(args) + "):"
                    lines.append(sig)
    
    if not lines:
        return "" # No structural elements like classes or functions
        
    return "\n".join(lines)


def _generate_js_ts_map(file_path):
    """E9: Regex-based structural extraction for JavaScript/TypeScript files.
    
    Extracts: function declarations, arrow functions, class declarations,
    and method definitions.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return f"Could not read {file_path}: {e}"

    lines = []
    
    # Match: function name(args) or async function name(args)
    for m in re.finditer(r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)', content):
        lines.append(f"function {m.group(1)}({m.group(2).strip()})")
    
    # Match: const name = (...) => or const name = async (...) =>
    for m in re.finditer(r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*=>', content):
        lines.append(f"const {m.group(1)} = ({m.group(2).strip()}) =>")
    
    # Match: class Name extends Base {
    for m in re.finditer(r'(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?\s*\{', content):
        base = f"({m.group(2)})" if m.group(2) else ""
        lines.append(f"class {m.group(1)}{base}")
    
    # Match: method definitions like  methodName(args) {
    for m in re.finditer(r'^\s+(?:async\s+)?(\w+)\s*\(([^)]*)\)\s*\{', content, re.MULTILINE):
        name = m.group(1)
        if name not in ('if', 'for', 'while', 'switch', 'catch', 'function'):
            lines.append(f"  {name}({m.group(2).strip()})")
    
    return "\n".join(lines) if lines else ""


def _parse_file(file_path, file_name, rel_path,
                supported_ast_ext, js_ts_ext, other_supported_ext):
    """Parses a single file and returns (header, content) or None.

    O3: Designed for use with ThreadPoolExecutor for parallel I/O.
    O5: Implements mtime-based AST caching for speed optimization.
    """
    try:
        mtime = os.path.getmtime(file_path)
    except OSError:
        mtime = 0

    cache_key = str(file_path)
    if cache_key in _AST_CACHE:
        cached = _AST_CACHE[cache_key]
        if cached.get("mtime") == mtime and "content" in cached:
            return (f"--- FILE: {rel_path} ---", cached["content"])

    content = None
    if file_name.endswith(supported_ast_ext):
        ast_outline = _generate_python_map(file_path)
        content = ast_outline if ast_outline else "# No classes or functions defined."
    elif file_name.endswith(js_ts_ext):
        js_outline = _generate_js_ts_map(file_path)
        content = js_outline if js_outline else "# No functions or classes found."
    elif file_name.endswith(other_supported_ext):
        content = "# Non-python file. Full contents omitted from map."

    if content is not None:
        _AST_CACHE[cache_key] = {"mtime": mtime, "content": content}
        return (f"--- FILE: {rel_path} ---", content)
    
    return None


# Threshold for switching to parallel parsing
_PARALLEL_THRESHOLD = 10


def generate_repo_map(target_dir="your_project"):
    """
    Crawls the target directory and creates a unified index of all files.
    Python files get AST parsed. JS/TS files get regex parsed (E9).
    Other code files get listed.

    O3: Uses ThreadPoolExecutor for parallel file parsing in large repos.
    """
    if not os.path.exists(target_dir):
        return "Project directory is empty or does not exist."

    supported_ast_ext = (".py",)
    js_ts_ext = (".js", ".jsx", ".ts", ".tsx")
    other_supported_ext = (".go", ".html", ".css", ".md")
    all_supported = supported_ast_ext + js_ts_ext + other_supported_ext

    _load_cache()

    # Phase 1: Collect all files to parse
    files_to_parse = []  # (file_path, file_name, rel_path)
    
    for root, _, files in os.walk(target_dir):
        # Skip hidden directories like .git or .pytest_cache
        if "/." in root.replace("\\", "/") or "\\." in root:
            continue
        # Skip node_modules
        if "node_modules" in root:
            continue
            
        for file in files:
            if file.endswith(all_supported):
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, start=".")
                files_to_parse.append((file_path, file, rel_path))

    if not files_to_parse:
        return "No supported code files found."

    # Phase 2: Parse files (parallel for large repos, sequential for small)
    results = []  # (index, header, content)

    if len(files_to_parse) >= _PARALLEL_THRESHOLD:
        with ThreadPoolExecutor(max_workers=min(len(files_to_parse), 8)) as pool:
            future_to_idx = {}
            for idx, (fpath, fname, rpath) in enumerate(files_to_parse):
                future = pool.submit(
                    _parse_file, fpath, fname, rpath,
                    supported_ast_ext, js_ts_ext, other_supported_ext
                )
                future_to_idx[future] = idx

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    result = future.result()
                    if result:
                        results.append((idx, result[0], result[1]))
                except Exception:
                    pass
    else:
        for idx, (fpath, fname, rpath) in enumerate(files_to_parse):
            result = _parse_file(
                fpath, fname, rpath,
                supported_ast_ext, js_ts_ext, other_supported_ext
            )
            if result:
                results.append((idx, result[0], result[1]))

    if not results:
        return "No supported code files found."

    # Phase 3: Sort by original file order and assemble
    results.sort(key=lambda x: x[0])
    repo_map = []
    for _, header, content in results:
        repo_map.append(header)
        repo_map.append(content)
        repo_map.append("")  # spacer

    _save_cache()
    return "\n".join(repo_map)

if __name__ == "__main__":
    print("Generating Testing Repo Map:")
    print(generate_repo_map("scripts"))
