import subprocess
import os
import requests
from github import Github

# Local Model Execution parameters
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:3b")

# GitHub Context for Inline Reviews Context
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
PR_NUMBER = os.getenv("PR_NUMBER")
REPO_NAME = os.getenv("GITHUB_REPOSITORY")
COMMIT_SHA = os.getenv("COMMIT_SHA")
IS_LOCAL = os.getenv("LOCAL_MODE", "false").lower() == "true"

def ai_generate(prompt):
    """Hits the local Ollama API to generate code/text."""
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_ctx": 8192
        }
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=300)
        response.raise_for_status()
        return response.json()['response']
    except Exception as e:
        print(f"Error calling Ollama API: {e}")
        return ""

def post_inline_comment(file_path, line_number, comment):
    """Post an inline comment on a Pull Request."""
    if IS_LOCAL or not all([GITHUB_TOKEN, PR_NUMBER, REPO_NAME, COMMIT_SHA]):
        print(f"\n[Local Review] {file_path}:{line_number} -> {comment}\n")
        return

    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        pr = repo.get_pull(int(PR_NUMBER))
        pr.create_review_comment(
            body=f"🤖 **Reviewer Agent Suggestion:**\n{comment}",
            commit_id=repo.get_commit(COMMIT_SHA),
            path=file_path,
            line=int(line_number)
        )
    except Exception as e:
        print(f"Failed to post PR comment: {e}")

def get_modified_files():
    """Smart Git Diff: Returns list of modified files in the PR."""
    supported_ext = (".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".html", ".css")
    if IS_LOCAL:
        files = []
        for root, _, fs in os.walk("your_project"):
            for f in fs:
                if f.endswith(supported_ext):
                    files.append(os.path.join(root, f))
        return files
        
    try:
        base_ref = os.getenv("GITHUB_BASE_REF", "main")
        output = subprocess.check_output(
            ["git", "diff", f"origin/{base_ref}...HEAD", "--name-only"], 
            text=True
        )
        return [f.strip() for f in output.split("\n") if f.strip() and f.startswith("your_project/")]
    except Exception as e:
        print(f"Failed to get modified files: {e}")
        return [os.path.join(r, f) for r, d, fs in os.walk("your_project") for f in fs]

def ensure_code_exists():
    """Initial repo bootstrap rule with Multi-File extraction."""
    supported_ext = (".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".html", ".css")
    if not any(f.endswith(supported_ext) for _,_,files in os.walk("your_project") for f in files):
        if os.path.exists("prompt.txt"):
            prompt = open("prompt.txt").read()
            # Advanced generation prompt requiring structured output
            advanced_prompt = (
                f"Generate a complete implementation for the following prompt: {prompt}\n"
                "You must organize your output into distinct files. For each file you generate, strictly use the following delimiter format:\n"
                "--- FILE: <file_path_relative_to_root> ---\n"
                "<code>\n\n"
                "Example:\n"
                "--- FILE: src/index.html ---\n"
                "<!DOCTYPE html><html>...</html>\n"
                "--- FILE: src/styles/main.css ---\n"
                "body { color: red; }\n\n"
                "Return ONLY the delimiter blocks and the exact file contents."
            )
            print("No code found! Designing foundation infrastructure...")
            raw_output = ai_generate(advanced_prompt)
            
            # The python logic to parse the multiplexed multi-files out of the LLM stream
            os.makedirs("your_project", exist_ok=True)
            current_file_path = None
            current_content = []
            
            for line in raw_output.split("\n"):
                if line.startswith("--- FILE:") and line.endswith("---"):
                    # Save the previous file if one was tracked
                    if current_file_path:
                        normalized_path = os.path.normpath(current_file_path.strip().lstrip('/'))
                        write_path = os.path.join("your_project", normalized_path)
                        os.makedirs(os.path.dirname(write_path), exist_ok=True)
                        with open(write_path, "w") as f:
                            f.write("\n".join(current_content).strip())
                    
                    # Capture the new file path from regex-style extraction
                    extracted_path = line.replace("--- FILE:", "").replace("---", "").strip()
                    # Sanitize paths to avoid writing outside your_project
                    if ".." in extracted_path: 
                        extracted_path = extracted_path.replace("..", "")
                        
                    current_file_path = extracted_path
                    current_content = []
                else:
                    if current_file_path is not None:
                        current_content.append(line)
            
            # Write the final tracked file at the EOF
            if current_file_path:
                normalized_path = os.path.normpath(current_file_path.strip().lstrip('/'))
                write_path = os.path.join("your_project", normalized_path)
                os.makedirs(os.path.dirname(write_path), exist_ok=True)
                with open(write_path, "w") as f:
                    f.write("\n".join(current_content).strip())
            
            # Fallback if the LLM ignored strict instructions and just barfed single code block
            if not current_file_path and raw_output.strip():
                with open("your_project/generated_code.txt", "w") as f:
                    f.write(raw_output)

# =========================================================================
# Multi-Agent Workflow
# =========================================================================

def run_critic(file_path, language):
    """
    Agent 1 (The Critic): Runs linters and security scanners.
    Now optimized with Web Linters (HTML/CSS/TS).
    """
    diagnostics = ""
    print(f"[Critic] Analyzing {file_path}...")
    if language == "Python":
        diagnostics += subprocess.getoutput(f"pylint {file_path}") + "\n"
        diagnostics += subprocess.getoutput(f"bandit -r {file_path}") + "\n"
    elif language == "JavaScript" or language == "TypeScript":
        diagnostics += subprocess.getoutput(f"eslint {file_path}") + "\n"
        if language == "JavaScript":
            diagnostics += subprocess.getoutput(f"njsscan {file_path}") + "\n"
    elif language == "Go":
        diagnostics += subprocess.getoutput(f"golint {file_path}") + "\n"
        diagnostics += subprocess.getoutput(f"gosec {file_path}") + "\n"
    elif language == "HTML":
        diagnostics += subprocess.getoutput(f"htmlhint {file_path}") + "\n"
    elif language == "CSS":
        diagnostics += subprocess.getoutput(f"stylelint {file_path}") + "\n"

    return diagnostics

def run_engineer(file_path, original_code, diagnostics, language):
    """
    Agent 2 (The Engineer): Receives Critic output and rewrites code to fix it.
    Returns the fixed code without inline annotations.
    """
    print(f"[Engineer] Repairing {file_path} based on Critic feedback...")
    prompt = (
        f"Language: {language}\n"
        f"Code:\n{original_code}\n\n"
        f"Critic Issues:\n{diagnostics}\n\n"
        "You are the Engineer Agent. Please provide the corrected file content. "
        "Return ONLY the code, no markdown formatting blocks, and no explanations."
    )
    fixed_code_response = ai_generate(prompt)

    # Clean markdown fences if any slipped through
    lines = fixed_code_response.split('\n')
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
        
    fixed_code = "\n".join(lines).strip()
    
    # Save the fixed code immediately
    with open(file_path, "w") as f:
        f.write(fixed_code)
        
    return fixed_code

def run_reviewer(file_path, original_code, fixed_code, language):
    """
    Agent 3 (The Reviewer): Inspects the difference and writes the PR comments.
    """
    print(f"[Reviewer] Explaining fixes for {file_path}...")
    prompt = (
        f"Language: {language}\n"
        f"Original Code:\n{original_code}\n"
        f"Engineer Fixed Code:\n{fixed_code}\n"
        "You are the Reviewer Agent. Explain the changes the Engineer made to fix the issues "
        "and improve security/quality. Format your response STRICTLY line by line like this:\n"
        "COMMENT_LINE: <line_number_in_fixed_code>|<short explanation of the fix>\n"
        "Do not output anything else."
    )
    explanation_response = ai_generate(prompt)
    
    for line in explanation_response.split('\n'):
        if line.startswith("COMMENT_LINE:"):
            try:
                _, data = line.split(":", 1)
                line_num, comment_txt = data.split("|", 1)
                post_inline_comment(file_path, int(line_num.strip()), comment_txt.strip())
            except Exception:
                pass


def run_pipeline(max_iterations=3):
    ensure_code_exists()
    files_to_review = get_modified_files()
    
    for path in files_to_review:
        if not os.path.exists(path):
            continue
            
        language = ""
        if path.endswith(".py"): language = "Python"
        elif path.endswith((".js", ".jsx")): language = "JavaScript"
        elif path.endswith((".ts", ".tsx")): language = "TypeScript"
        elif path.endswith(".go"): language = "Go"
        elif path.endswith(".html"): language = "HTML"
        elif path.endswith(".css"): language = "CSS"
        
        if language:
            for i in range(max_iterations):
                # Phase 1: Critic
                diagnostics = run_critic(path, language)
                
                if "error" in diagnostics.lower() or "warning" in diagnostics.lower():
                    # Read original state
                    with open(path, "r") as f:
                        original_code = f.read()
                        
                    # Phase 2: Engineer (Fixes the code)
                    fixed_code = run_engineer(path, original_code, diagnostics, language)
                    
                    # Phase 3: Reviewer (Explains the fixes via GitHub PR comments)
                    run_reviewer(path, original_code, fixed_code, language)
                else:
                    print(f"✅ [Critic] {path} passed analysis cleanly.")
                    break

import sys

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--manual":
        # Manual prompt override mode handles scaffold generation
        ensure_code_exists()
    else:
        # Standard code review / patching pipeline
        run_pipeline()

if __name__ == "__main__":
    main()
