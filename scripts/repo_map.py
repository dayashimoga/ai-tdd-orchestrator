import os
import ast

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


def generate_repo_map(target_dir="your_project"):
    """
    Crawls the target directory and creates a unified index of all files.
    Python files get AST parsed. Other code files get listed.
    """
    if not os.path.exists(target_dir):
        return "Project directory is empty or does not exist."

    supported_ast_ext = (".py",)
    other_supported_ext = (".js", ".jsx", ".ts", ".tsx", ".go", ".html", ".css", ".md")
    
    repo_map = []
    
    for root, _, files in os.walk(target_dir):
        # Skip hidden directories like .git or .pytest_cache
        if "/." in root.replace("\\", "/") or "\\." in root:
            continue
            
        for file in files:
            file_path = os.path.join(root, file)
            # Normalize for consistent display
            rel_path = os.path.relpath(file_path, start=".")
            
            if file.endswith(supported_ast_ext):
                repo_map.append(f"--- FILE: {rel_path} ---")
                ast_outline = _generate_python_map(file_path)
                if ast_outline:
                    repo_map.append(ast_outline)
                else:
                    repo_map.append("# No classes or functions defined.")
                repo_map.append("") # spacer
            elif file.endswith(other_supported_ext):
                repo_map.append(f"--- FILE: {rel_path} ---")
                repo_map.append("# Non-python file. Full contents omitted from map.")
                repo_map.append("") # spacer

    if not repo_map:
        return "No supported code files found."
        
    return "\n".join(repo_map)

if __name__ == "__main__":
    print("Generating Testing Repo Map:")
    print(generate_repo_map("scripts"))
