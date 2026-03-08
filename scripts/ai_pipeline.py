"""AI TDD Orchestrator Pipeline — V5 Optimized.

Autonomous code generation, testing, and remediation using local LLMs.
Supports: --manual, --issue, --resume-with-hint, --index-docs, --dry-run CLI modes.
"""
import subprocess
import os
import sys
import json
import re
import ast as ast_module
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional, Dict, Any

import requests
from github import Github

# Add repository root to Python path so 'scripts.*' imports resolve
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import scripts.repo_map as repo_map
import scripts.gpu_platform as gpu_platform
import scripts.llm_router as llm_router
import scripts.rag_engine as rag_engine

# ---------------------------------------------------------------------------
# Configuration (all env-configurable)
# ---------------------------------------------------------------------------
# Auto-detect the best GPU platform from environment variables
# PS2: Deferred to first use — do NOT call at import time to save ~5s startup
_detected_platform: Optional[str] = None
_detected_url: Optional[str] = None

def _get_platform_url() -> str:
    """PS2: Lazy platform detection — only called when first needed."""
    global _detected_platform, _detected_url
    if _detected_url is None:
        _detected_platform, _detected_url = gpu_platform.select_platform()
    return _detected_url

# os.getenv returns "" if the secret is empty but passed by GH Actions
OLLAMA_URL: str = os.getenv("OLLAMA_URL") or ""
MODEL_NAME: str = os.getenv("OLLAMA_MODEL") or "qwen2.5-coder:3b"
NUM_CTX: int = int(os.getenv("OLLAMA_NUM_CTX") or "8192")
MAX_TDD_ITERATIONS: int = int(os.getenv("MAX_TDD_ITERATIONS") or "15")
MAX_RETRIES_PER_TASK: int = int(os.getenv("MAX_RETRIES_PER_TASK") or "5")

GITHUB_TOKEN: Optional[str] = os.getenv("GITHUB_TOKEN")
TARGET_REPO_TOKEN: Optional[str] = os.getenv("TARGET_REPO_TOKEN") or GITHUB_TOKEN
PR_NUMBER: Optional[str] = os.getenv("PR_NUMBER")
REPO_NAME: Optional[str] = os.getenv("GITHUB_REPOSITORY")
COMMIT_SHA: Optional[str] = os.getenv("COMMIT_SHA")
IS_LOCAL: bool = os.getenv("LOCAL_MODE", "false").lower() == "true"
PROJECT_TYPE: str = os.getenv("PROJECT_TYPE", "new")
TARGET_REPO: str = os.getenv("TARGET_REPO", "")
DRY_RUN: bool = "--dry-run" in sys.argv

GIT_TIMEOUT: int = 120  # seconds — prevents infinite CI hangs

# ---------------------------------------------------------------------------
# Compiled Regex Patterns (O4) — compiled once at module load, not per-call
# ---------------------------------------------------------------------------
_RE_ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
_RE_FILE_DELIMITER = re.compile(r'^--- FILE:\s*(.+?)\s*---$', re.MULTILINE)
_RE_CODE_BLOCK = re.compile(r'```(?:[a-zA-Z0-9_-]+)?\s*\n(.*?)\n?```', re.DOTALL)
_RE_ERROR_TYPES = re.compile(r'ImportError|SyntaxError|NameError|ModuleNotFoundError|TypeError|AttributeError|IndentationError')

# Runtime caches (cleared between tasks, preserved across retries)
_repo_map_cache: Optional[str] = None
_discovery_cache: Dict[str, List[str]] = {}

# ---------------------------------------------------------------------------
# Shared Utilities
# ---------------------------------------------------------------------------

def get_github_client(token: Optional[str] = None) -> Github:
    """Creates a single reusable PyGithub client."""
    return Github(token or TARGET_REPO_TOKEN or GITHUB_TOKEN)


def mask_secret(text: str, secret: Optional[str]) -> str:
    """Replaces secret tokens in log text with '***' to prevent leaks."""
    if secret and len(secret) > 4:
        return text.replace(secret, "***")
    return text


def safe_path(path: str, sandbox: str = "your_project") -> Optional[str]:
    """Validates and sandboxes a file path using realpath.
    Auto-prepends the sandbox directory if the LLM omitted it.
    """
    normalized = os.path.normpath(path.strip().lstrip("/"))
    
    # CG9: If LLM generated "app.py" instead of "your_project/app.py", auto-prefix it
    if not normalized.startswith(sandbox) and not normalized.startswith(sandbox + os.sep):
        normalized = os.path.normpath(os.path.join(sandbox, normalized))
        print(f"  ⚠️ Auto-prefixed missing sandbox directory: -> {normalized}")
        
    real = os.path.realpath(normalized)
    sandbox_real = os.path.realpath(sandbox)
    if not real.startswith(sandbox_real):
        print(f"  ❌ Security reject: {path} escapes sandbox {sandbox}")
        return None
    return normalized


def git_run(args: List[str], cwd: str = "your_project", **kwargs) -> subprocess.CompletedProcess:
    """Runs a git command with timeout and secrets masking."""
    kwargs.setdefault("timeout", GIT_TIMEOUT)
    result = subprocess.run(args, cwd=cwd, **kwargs)
    return result


def truncate_feedback(feedback: str, max_lines: int = 50) -> str:
    """Truncates error feedback and strips ANSI escape codes."""
    clean = _RE_ANSI_ESCAPE.sub('', feedback)
    lines = clean.strip().split('\n')
    if len(lines) > max_lines:
        return '\n'.join(lines[-max_lines:])
    return clean


def extract_test_failures(raw_feedback: str) -> str:
    """TF1: Extracts only the failing test names and assertion errors from pytest output.

    Instead of dumping the full traceback into the retry prompt, this extracts
    a concise summary that is more actionable for the LLM.
    """
    lines = raw_feedback.split('\n')
    failures: List[str] = []
    current_failure = ""
    in_failure = False

    for line in lines:
        # Capture FAILED test names
        if 'FAILED' in line and '::' in line:
            failures.append(line.strip())
        # Capture assertion errors
        if 'AssertionError' in line or 'assert ' in line.lower():
            failures.append(line.strip())
        # Capture key error lines (E keyword in pytest short summary)
        if line.strip().startswith('E ') and len(line.strip()) > 2:
            failures.append(line.strip())
        # Capture import/syntax/name errors (O5: compiled regex)
        if _RE_ERROR_TYPES.search(line):
            failures.append(line.strip())
        # Capture short test summary info block
        if 'short test summary' in line.lower():
            in_failure = True
            continue
        if in_failure and line.strip():
            failures.append(line.strip())
        if in_failure and not line.strip():
            in_failure = False

    # Extract Code Coverage Missing Lines
    if "Required test coverage" in raw_feedback:
        failures.append("\n⚠️ TESTS PASSED, BUT CODE COVERAGE DROPPED BELOW 90%!")
        failures.append("You MUST add test cases for the following missing lines:")
        in_coverage_table = False
        for line in lines:
            if line.startswith("Name ") and "Miss" in line and "Missing" in line:
                in_coverage_table = True
                continue
            if line.startswith("-----") and in_coverage_table:
                continue
            if line.startswith("TOTAL") and in_coverage_table:
                in_coverage_table = False
                break
            
            if in_coverage_table and line.strip():
                parts = line.split()
                if len(parts) >= 5: # Name, Stmts, Miss, Cover, Missing...
                    # If there's missing lines, they start from index 4 onwards
                    file_name = parts[0]
                    missing_lines = " ".join(parts[4:])
                    if missing_lines:
                        failures.append(f"  - {file_name}: lines {missing_lines}")

    # D1: Detect missing module errors and guide the LLM to fix requirements.txt
    if "ModuleNotFoundError" in raw_feedback or "No module named" in raw_feedback:
        import re as _re2
        missing_modules = _re2.findall(r"No module named '([^']+)'", raw_feedback)
        if missing_modules:
            failures.append("\n❌ CRITICAL: ModuleNotFoundError detected!")
            failures.append("The following modules are NOT installed: " + ", ".join(set(missing_modules)))
            failures.append("You MUST generate a '--- FILE: requirements.txt ---' containing these packages.")
            failures.append("Example: If you use flask, add 'flask>=3.0' to requirements.txt.")

    if not failures:
        # Fallback: return truncated version
        return truncate_feedback(raw_feedback, max_lines=30)

    return '\n'.join(dict.fromkeys(failures))  # deduplicate while preserving order


def validate_python_syntax(content: str, file_path: str) -> Tuple[bool, str]:
    """E5: Validates Python syntax using ast.parse before writing to disk."""
    if not file_path.endswith('.py'):
        return True, ""
    try:
        ast_module.parse(content)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError in {file_path} line {e.lineno}: {e.msg}"


def validate_llm_response(raw_output: str) -> Tuple[bool, str]:
    """E8: Validates the LLM response contains expected file delimiters.

    Returns (is_valid, error_message). If invalid, the caller should
    retry the LLM call immediately instead of running the test suite.
    """
    if not raw_output or not raw_output.strip():
        return False, "LLM returned empty response"

    # Check for at least one file delimiter (O4: compiled regex)
    file_blocks = _RE_FILE_DELIMITER.findall(raw_output)
    if not file_blocks:
        # Check if the LLM returned conversational text instead of code
        if len(raw_output) > 50 and '```' not in raw_output:
            return False, "LLM response contains no code blocks or file delimiters"
        return False, "No '--- FILE: path ---' delimiters found in response"

    return True, ""


def _sanitize_generated_code(content: str, file_path: str) -> str:
    """CG5: Post-process generated code to fix common LLM output issues.
    
    1. Strips conversational text that the LLM embeds after code blocks
    2. Fixes 'from your_project.X import' → 'from X import' (incorrect absolute imports)
    3. Removes markdown artifacts left inside code
    """
    lines = content.split('\n')
    cleaned_lines = []
    for line in lines:
        # Skip lines that look like conversational English prose (not code)
        stripped = line.strip()
        if stripped and not stripped.startswith('#') and not stripped.startswith('"""') and not stripped.startswith("'''"):
            # Detect conversational text: long lines with no code characters
            if (len(stripped) > 60 
                and '=' not in stripped 
                and '(' not in stripped 
                and ')' not in stripped
                and ':' not in stripped
                and 'import' not in stripped
                and not stripped.startswith('def ')
                and not stripped.startswith('class ')
                and not stripped.startswith('@')
                and not stripped.startswith('raise ')
                and not stripped.startswith('return ')
                and not stripped.startswith('assert ')
                and file_path.endswith('.py')):
                print(f"  ⚠️ Stripped conversational text from {file_path}: '{stripped[:60]}...'")
                continue
        cleaned_lines.append(line)
    
    content = '\n'.join(cleaned_lines)
    
    # Fix incorrect absolute imports: 'from your_project.X import' → 'from X import'
    content = re.sub(r'from\s+your_project\.', 'from ', content)
    content = re.sub(r'import\s+your_project\.', 'import ', content)
    
    return content


def parse_and_write_files(raw_output: str, target_dir: str = "your_project") -> int:
    """Parses LLM '--- FILE: path ---' delimited output and writes files.

    Includes E5 syntax validation and CG5 post-processing before writing.
    CG6: Refuses to write syntax-invalid Python files (prevents broken files
    from being committed into rollback snapshots).
    Returns the number of files written.
    """
    files_written = 0
    syntax_errors: List[str] = []
    # Split by standard delimiter (O4: compiled regex)
    parts = _RE_FILE_DELIMITER.split(raw_output)
    
    for i in range(1, len(parts), 2):
        if i + 1 >= len(parts):
            break
        
        file_path = parts[i].strip()
        raw_content = parts[i+1]
        
        # Strip trailing conversational fluff (O4: compiled regex)
        match = _RE_CODE_BLOCK.search(raw_content)
        if match:
            content = match.group(1).strip()
        else:
            content = raw_content.strip()
            
        if content:
            # CG5: Post-process to fix common LLM mistakes
            content = _sanitize_generated_code(content, file_path)
            
            # E5 + CG6: Syntax validation — REFUSE to write invalid Python files
            valid, err = validate_python_syntax(content, file_path)
            if not valid:
                syntax_errors.append(err)
                print(f"❌ REJECTED {file_path}: {err} — file NOT written (prevents snapshot pollution)")
                continue  # CG6: Skip writing this broken file entirely

            validated = safe_path(file_path, target_dir)
            if validated:
                write_path = os.path.join(target_dir, validated) if not validated.startswith(target_dir) else validated
                os.makedirs(os.path.dirname(write_path), exist_ok=True)
                with open(write_path, "w", encoding="utf-8") as f:
                    f.write(content + "\n")
                files_written += 1

    if syntax_errors:
        print(f"\n⚠️ {len(syntax_errors)} Python file(s) REJECTED due to syntax errors")

    return files_written

# ---------------------------------------------------------------------------
# Core LLM Interface
# ---------------------------------------------------------------------------

def ai_generate(prompt: str) -> str:
    """Routes generation to the configured LLM provider via llm_router."""
    return llm_router.generate(prompt, stream=True, temperature=0.2, num_ctx=NUM_CTX)


def post_inline_comment(file_path: str, line_number: int, comment: str) -> None:
    """Post an inline comment on a Pull Request."""
    if IS_LOCAL or not all([GITHUB_TOKEN, PR_NUMBER, REPO_NAME, COMMIT_SHA]):
        print(f"\n[Local Review] {file_path}:{line_number} -> {comment}\n")
        return
    try:
        g = get_github_client(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        pr = repo.get_pull(int(PR_NUMBER))
        pr.create_review_comment(
            body=f"🤖 **Reviewer Agent Suggestion:**\n{comment}",
            commit_id=repo.get_commit(COMMIT_SHA),
            path=file_path,
            line=int(line_number),
        )
    except Exception as e:
        print(f"Failed to post PR comment: {e}")


def get_modified_files() -> List[str]:
    """Returns list of modified files in the PR or project dir."""
    supported_ext = (".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".html", ".css")
    if IS_LOCAL:
        files: List[str] = []
        for root, _, fs in os.walk("your_project"):
            for f in fs:
                if f.endswith(supported_ext):
                    files.append(os.path.join(root, f))
        return files
    try:
        base_ref = os.getenv("GITHUB_BASE_REF") or "main"
        output = subprocess.check_output(
            ["git", "diff", f"origin/{base_ref}...HEAD", "--name-only"],
            text=True, timeout=GIT_TIMEOUT,
        )
        return [f.strip() for f in output.split("\n") if f.strip() and f.startswith("your_project/")]
    except Exception as e:
        print(f"Failed to get modified files: {e}")
        return [os.path.join(r, f) for r, _, fs in os.walk("your_project") for f in fs]

# ---------------------------------------------------------------------------
# Repository Management
# ---------------------------------------------------------------------------

def setup_target_repository() -> None:
    """Clones an existing repo or creates a new one."""
    global TARGET_REPO, PROJECT_TYPE
    if not TARGET_REPO:
        print("⚠️ No TARGET_REPO provided. Operating locally in 'your_project'.")
        return

    if os.path.exists("your_project"):
        shutil.rmtree("your_project")

    if PROJECT_TYPE == "existing":
        print(f"🔄 Cloning existing project: {TARGET_REPO}")
        clone_url = f"https://oauth2:{TARGET_REPO_TOKEN}@github.com/{TARGET_REPO}.git"
        git_run(["git", "clone", clone_url, "your_project"], cwd=".", check=True)
        print("✅ Clone complete.")
    else:
        print(f"✨ Creating new project repository: {TARGET_REPO}")
        os.makedirs("your_project", exist_ok=True)
        try:
            g = get_github_client(TARGET_REPO_TOKEN)
            user = g.get_user()
            repo_name = TARGET_REPO.split("/")[-1]
            repo = user.create_repo(repo_name, private=True)
            print(f"✅ Created remote repository: {repo.html_url}")
            
            # Update TARGET_REPO to the full full_name (e.g., username/repo_name)
            # so the remote_url below is correctly formatted.
            TARGET_REPO = repo.full_name
        except Exception as e:
            error_msg = mask_secret(str(e), TARGET_REPO_TOKEN)
            print(f"❌ Error: Could not create remote repository: {error_msg}")
            
            # Auto-fallback: if the repo already exists, switch to 'existing' mode
            if "name already exists on this account" in str(e).lower() or "422" in str(e):
                print("👉 Auto-detecting existing repository. Falling back to cloning instead of creating...")
                PROJECT_TYPE = "existing"
                # Ensure TARGET_REPO has the owner prefix for cloning (e.g., username/repo_name)
                if "/" not in TARGET_REPO:
                    try:
                        # 'user' is already defined in the try block above
                        TARGET_REPO = f"{user.login}/{TARGET_REPO}"
                    except Exception:
                        pass # Fallback to original string if PyGithub fails
                return setup_target_repository()

            if "403" in str(e) or "Forbidden" in str(e) or "404" in str(e):
                print("👉 Hint: The default GitHub Actions token cannot create new repositories.")
                print("👉 Please create a Personal Access Token (PAT) with 'repo' scope and add it to secrets.TARGET_REPO_TOKEN.")
            else:
                print("👉 Hint: If the repository already exists, please run the pipeline with project_type='existing'.")
            sys.exit(1)

        git_run(["git", "init"], check=True)
        git_run(["git", "checkout", "-b", "main"])

        try:
            workflow_dir = os.path.join("your_project", ".github", "workflows")
            os.makedirs(workflow_dir, exist_ok=True)
            workflow_path = os.path.join(workflow_dir, "python-test.yml")
            with open(workflow_path, "w") as f:
                f.write("name: CI\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-python@v5\n        with:\n          python-version: '3.11'\n      - run: pip install pytest pytest-cov\n      - run: pip install -r requirements.txt || true\n      - run: pytest --cov=./ --cov-fail-under=90")

            git_run(["git", "add", "."], check=True)
            
            # Briefly set author so initial commit works
            git_run(["git", "config", "user.name", "ai-orchestrator"], check=False)
            git_run(["git", "config", "user.email", "actions@github.com"], check=False)
            
            git_run(["git", "commit", "-m", "chore: setup AI orchestrator repo"], check=False)
        except Exception:
            pass

        remote_url = f"https://oauth2:{TARGET_REPO_TOKEN}@github.com/{TARGET_REPO}.git"
        git_run(["git", "remote", "add", "origin", remote_url], check=True)
        try:
            git_run(["git", "push", "-u", "origin", "main"], check=True)
            print("✅ Initializer workflow pushed to remote.")
        except Exception as e:
            print(f"⚠️ Failed to push initialization to remote: {mask_secret(str(e), TARGET_REPO_TOKEN)}")

    # E1: Unconditionally apply git author configs so rollback commits succeed in TDD loop for both new AND existing cloned repos
    git_run(["git", "config", "user.name", "ai-orchestrator"], check=False)
    git_run(["git", "config", "user.email", "actions@github.com"], check=False)


def push_to_target_repository() -> None:
    """Commits and pushes changes directly to the target repo."""
    if not TARGET_REPO:
        return

    print(f"\n🚀 Pushing completed AI generation to {TARGET_REPO} ...")
    try:
        git_run(["git", "config", "user.name", "ai-orchestrator"])
        git_run(["git", "config", "user.email", "actions@github.com"])
        git_run(["git", "add", "."], check=True)

        status = git_run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if not status.stdout.strip():
            print("✅ No changes to commit.")
            return

        git_run(["git", "commit", "-m", "feat: autonomous AI generation and TDD fixes"], check=True)

        remote_url = f"https://oauth2:{TARGET_REPO_TOKEN}@github.com/{TARGET_REPO}.git"
        remotes = git_run(["git", "remote", "-v"], capture_output=True, text=True).stdout
        if "origin" not in remotes:
            git_run(["git", "remote", "add", "origin", remote_url], check=True)
        else:
            git_run(["git", "remote", "set-url", "origin", remote_url], check=True)

        git_run(["git", "push", "origin", "main"], check=True)
        print("✅ Successfully pushed AI generated code to target repository.")
    except Exception as e:
        print(f"❌ Failed to commit and push changes: {mask_secret(str(e), TARGET_REPO_TOKEN)}")

# ---------------------------------------------------------------------------
# Code Scaffolding
# ---------------------------------------------------------------------------

def ensure_code_exists() -> None:
    """Initial repo bootstrap rule with Multi-File extraction."""
    supported_ext = (".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".html", ".css")
    if not any(f.endswith(supported_ext) for _, _, files in os.walk("your_project") for f in files):
        if os.path.exists("prompt.txt"):
            with open("prompt.txt", "r") as pf:
                prompt = pf.read()
            advanced_prompt = (
                f"You are bootstrapping a new project. Project Requirements:\n{prompt}\n\n"
                "Generate a complete, fully functional initial implementation. DO NOT generate dummy code or placeholders.\n"
                "You must organize your output into distinct files. For each file you generate, strictly use the following delimiter format:\n"
                "--- FILE: <file_path_relative_to_root> ---\n```python\n<body>\n```\n\n"
                "Example:\n--- FILE: src/main.py ---\n```python\nprint('Hello')\n```\n\n"
                "Return ONLY the delimiter blocks and code."
            )
            print("\n==============================================")
            print("🚀 SOFTWARE FACTORY: BOOTSTRAPPING SCAFFOLD")
            print("==============================================")
            print(f"📄 INITIAL PROMPT:\n{prompt.strip()}")
            print("==============================================\n")
            print("🧠 AI is currently designing the multi-file architecture and writing the codebase. Please wait...\n")

            raw_output = ai_generate(advanced_prompt)
            print("✅ AI Codebase Generation Complete. Synchronizing files to disk...\n")

            os.makedirs("your_project", exist_ok=True)
            files_written = parse_and_write_files(raw_output, "your_project")

            # Fallback if LLM ignored structured instructions
            if files_written == 0 and raw_output.strip():
                with open("your_project/generated_code.txt", "w") as f:
                    f.write(raw_output)

# =========================================================================
# Autonomous TDD & Task Planning Workflow
# =========================================================================

def generate_task_plan(prompt: str) -> None:
    """Agent 1 (The Planner): Generates a strict Markdown task checklist."""
    print("\n[Planner] Analyzing requirements and creating execution plan...")
    req_path = "your_project/docs/requirements.md"
    os.makedirs(os.path.dirname(req_path), exist_ok=True)
    with open(req_path, "w", encoding="utf-8") as f:
        f.write(f"# Project Requirements\n\n{prompt}\n")

    plan_prompt = (
        f"Based on the following project requirements: {prompt}\n\n"
        "Create a comprehensive implementation plan as a strict Markdown checklist.\n"
        "Break the work down into detailed, actionable steps (e.g., '- [ ] Create models.py with User schema', not just '- [ ] Core Logic').\n"
        "Ensure there is a step for writing comprehensive Pytest unit tests.\n"
        "Output ONLY the markdown checklist formatted exactly like this:\n"
        "- [ ] Detailed step 1\n"
        "- [ ] Detailed step 2\n"
        "- [ ] Write comprehensive unit tests\n"
    )
    plan_output = ai_generate(plan_prompt)

    with open("your_project/project_tasks.md", "w", encoding="utf-8") as f:
        f.write(plan_output)
    print(plan_output)

    step_summary_file = os.getenv("GITHUB_STEP_SUMMARY")
    if step_summary_file and os.path.exists(step_summary_file):
        with open(step_summary_file, "a") as f:
            f.write("## 📋 AI Task Planner Checklist\n\n")
            f.write(plan_output + "\n\n")


def update_task_plan(new_prompt: str) -> None:
    """Agent 1 (The Planner): Updates the execution plan for new requirements."""
    print("\n[Planner] Updating requirements and execution plan...")
    req_path = "your_project/docs/requirements.md"
    os.makedirs(os.path.dirname(req_path), exist_ok=True)
    
    if os.path.exists(req_path):
        with open(req_path, "r", encoding="utf-8") as f:
            existing_reqs = f.read()
            
        if new_prompt.strip() not in existing_reqs:
            with open(req_path, "a", encoding="utf-8") as f:
                f.write(f"\n\n## New Requirements (Update)\n{new_prompt}\n")
    else:
        with open(req_path, "w", encoding="utf-8") as f:
            f.write(f"# Project Requirements\n\n{new_prompt}\n")

    tasks_path = "your_project/project_tasks.md"
    if not os.path.exists(tasks_path):
        print("⚠️ No tasks.md found to update.")
        return

    with open(tasks_path, "r", encoding="utf-8") as f:
        existing_plan = f.read()

    plan_prompt = (
        f"We have an existing project task list:\n{existing_plan}\n\n"
        f"The user has provided new requirements: {new_prompt}\n\n"
        "Update the task list to incorporate these new requirements. "
        "Keep completed tasks marked as '- [x]'. "
        "Add new tasks as '- [ ]' with descriptive, actionable instructions. "
        "Output ONLY the full updated markdown checklist."
    )
    plan_output = ai_generate(plan_prompt)
    with open("your_project/project_tasks.md", "w", encoding="utf-8") as f:
        f.write(plan_output)
    print(plan_output)

    step_summary_file = os.getenv("GITHUB_STEP_SUMMARY")
    if step_summary_file and os.path.exists(step_summary_file):
        with open(step_summary_file, "a") as f:
            f.write("## 📋 AI Task Planner Checklist (Updated)\n\n")
            f.write(plan_output + "\n\n")


def execute_task(task_description: str, use_cache: bool = False, base_task: str = "") -> int:
    """Agent 2 (The Engineer): Generates code with Repo Map context optimization.

    Args:
        task_description: The task or bug-fix prompt.
        use_cache: If True, reuse the cached repo map and discovery results
                   from a previous call (saves an LLM round-trip on retries).
        base_task: The original task name (stable across retries) for cache keys.
    
    Returns:
        Number of files written (0 if LLM failed completely).
    """
    global _repo_map_cache, _discovery_cache
    print(f"\n[Engineer] Executing Task: {task_description}")

    # O2: Cache repo map across retries
    if use_cache and _repo_map_cache:
        repo_map_content = _repo_map_cache
        print("♻️  Reusing cached repo map (retry iteration)")
    else:
        repo_map_content = repo_map.generate_repo_map("your_project")
        _repo_map_cache = repo_map_content

    # O3: Cache discovery results on retry — use stable base_task key
    cache_key = (base_task or task_description)[:80]
    if use_cache and cache_key in _discovery_cache:
        requested_files = _discovery_cache[cache_key]
        print(f"♻️  Reusing cached file discovery ({len(requested_files)} files)")
    else:
        discovery_prompt = (
            f"You are the Engineer Agent. Your current task is: {task_description}\n\n"
            f"Here is the structural map of the current codebase:\n{repo_map_content}\n\n"
            "To accomplish this task, which files do you need to read in their entirety? "
            "Return ONLY a comma-separated list of exact file paths. If you don't need any, return NONE."
        )
        print("🔍 Inspecting Repo Map to determine context window...")

        # CG2: Use llm_router instead of raw requests.post to respect LLM_PROVIDER
        try:
            requested_files_str = llm_router.generate(discovery_prompt, stream=False, temperature=0.1, num_ctx=4096)
        except Exception as e:
            print(f"Failed to query for files: {e}")
            requested_files_str = "NONE"

        requested_files = [f.strip() for f in requested_files_str.split(",") if f.strip() and f.strip() != "NONE"]
        _discovery_cache[cache_key] = requested_files

    context = f"--- REPO AST MAP ---\n{repo_map_content}\n\n--- FULL TARGET FILES ---\n"
    loaded_files = 0
    for file_path in requested_files:
        validated = safe_path(file_path)
        if validated and os.path.exists(validated) and os.path.isfile(validated):
            try:
                with open(validated, "r", encoding="utf-8", errors="ignore") as f:
                    context += f"\n--- FILE: {validated} ---\n{f.read()}\n"
                    loaded_files += 1
            except Exception:
                pass

    if loaded_files == 0:
        context += "(No full files loaded. Relying on map and generation capabilities.)\n"

    req_context = ""
    req_path = "your_project/docs/requirements.md"
    if os.path.exists(req_path):
        with open(req_path, "r", encoding="utf-8") as f:
           req_context = f.read()

    # RAG: Retrieve relevant reference document context
    rag_context = rag_engine.get_rag_context(task_description)
    if rag_context:
        print(f"📚 RAG: Injected reference document context into prompt")

    # CG1 + CG4: Enhanced engineer prompt with few-shot example and strict enforcement
    engineer_prompt = (
        f"You are the Engineer Agent. You MUST output ONLY code blocks using the exact delimiter format shown below.\n"
        f"Do NOT include explanations, commentary, or conversation. Output ONLY code.\n\n"
        f"--- PROJECT REQUIREMENTS ---\n{req_context}\n\n"
        f"{rag_context}"
        f"Your current granular task is: {task_description}\n\n"
        f"Here is your optimized project context:\n{context}\n\n"
        "Generate fully functional, production-ready code. DO NOT generate dummy or placeholder code.\n"
        "If the task involves testing, use `pytest` with descriptive test names.\n\n"
        "CRITICAL: You MUST ALWAYS generate a requirements.txt file listing ALL third-party dependencies "
        "(e.g. flask, fastapi, requests, sqlalchemy, etc.). Without this file, tests will fail with ModuleNotFoundError.\n\n"
        "CRITICAL: Do NOT include any explanations, descriptions, or English prose inside code files. "
        "Every line in a .py file must be valid Python syntax. Comments using # are fine.\n\n"
        "CRITICAL: Do NOT use 'from your_project.X import' — use 'from X import' instead. "
        "The project root is already on sys.path.\n\n"
        "OUTPUT FORMAT (you MUST follow this exactly):\n"
        "--- FILE: requirements.txt ---\n"
        "```\n"
        "flask>=3.0\n"
        "pytest>=8.0\n"
        "```\n\n"
        "--- FILE: app.py ---\n"
        "```python\n"
        "from flask import Flask\n\n"
        "app = Flask(__name__)\n"
        "```\n\n"
        "--- FILE: tests/test_app.py ---\n"
        "```python\n"
        "from app import app\n\n"
        "def test_app():\n"
        "    client = app.test_client()\n"
        "    assert client.get('/').status_code == 200\n"
        "```\n\n"
        "Now generate your code following this EXACT format. Output ONLY '--- FILE:' blocks and code. NO other text."
    )

    if DRY_RUN:
        print("\n🏜️  DRY RUN — skipping code generation. Would send this prompt:")
        print(engineer_prompt[:500] + "...")
        return 0

    # E8: Retry LLM if response is malformed (up to 2 extra attempts)
    raw_output = ""
    for attempt in range(3):
        raw_output = ai_generate(engineer_prompt)
        valid, err = validate_llm_response(raw_output)
        if valid:
            break
        print(f"⚠️ LLM response validation failed (attempt {attempt + 1}/3): {err}")
        if attempt < 2:
            print("🔄 Retrying LLM call...")

    files_written = parse_and_write_files(raw_output, "your_project")
    # Invalidate repo map cache after files change
    _repo_map_cache = None
    return files_written


def detect_test_command(project_dir: str = "your_project") -> List[str]:
    """E10: Auto-detect the appropriate test framework based on project files."""
    # Check for Python (pytest)
    if any(f.endswith(".py") for _, _, files in os.walk(project_dir) for f in files):
        return [sys.executable, "-m", "pytest", f"{project_dir}/", f"--cov={project_dir}/", "--cov-fail-under=90", "--cov-report=term-missing", "--no-header", "-q"]
    # Check for JavaScript/TypeScript (jest or npm test)
    if os.path.exists(os.path.join(project_dir, "package.json")):
        pkg_path = os.path.join(project_dir, "package.json")
        with open(pkg_path, "r") as f:
            pkg = json.loads(f.read())
        if "jest" in pkg.get("devDependencies", {}) or "jest" in pkg.get("dependencies", {}):
            return ["npx", "--prefix", project_dir, "jest", "--coverage"]
        return ["npm", "--prefix", project_dir, "test"]
    # Check for Go
    if any(f.endswith(".go") for _, _, files in os.walk(project_dir) for f in files):
        return ["go", "test", "-cover", f"./{project_dir}/..."]
    # Check for Rust
    if os.path.exists(os.path.join(project_dir, "Cargo.toml")):
        return ["cargo", "test", "--manifest-path", os.path.join(project_dir, "Cargo.toml")]
    # Default to pytest
    return [sys.executable, "-m", "pytest", f"{project_dir}/", f"--cov={project_dir}/", "--cov-fail-under=90", "--cov-report=term-missing", "--no-header", "-q"]


# Track installed deps to avoid redundant pip installs
_deps_installed_hash: str = ""


def _install_project_dependencies(project_dir: str = "your_project") -> None:
    """Auto-install project dependencies from requirements.txt before running tests.
    
    D1: Caches a hash of requirements.txt to skip redundant installs on retries.
    """
    global _deps_installed_hash
    req_file = os.path.join(project_dir, "requirements.txt")
    if os.path.exists(req_file):
        try:
            with open(req_file, "r") as f:
                content = f.read()
            import hashlib
            current_hash = hashlib.md5(content.encode()).hexdigest()
            if current_hash == _deps_installed_hash:
                print("\n📦 Dependencies already installed (unchanged). Skipping.")
                return
        except Exception:
            current_hash = ""

        print(f"\n📦 Installing dependencies from {req_file}...")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", req_file, "-q"],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                print("✅ Dependencies installed successfully.")
                _deps_installed_hash = current_hash
            else:
                print(f"⚠️ pip install warnings: {result.stderr[:300]}")
        except Exception as e:
            print(f"⚠️ Failed to install dependencies: {e}")
    else:
        print("ℹ️ No requirements.txt found in project. Skipping dependency install.")


def run_pytest_validation(retry_mode: bool = False) -> Tuple[bool, str]:
    """Execute the detected test framework natively to enforce TDD behavior.

    Args:
        retry_mode: If True, uses --lf (last-failed) to only re-run failing tests (TF3).
    """
    # D1: Auto-install project dependencies before running tests
    _install_project_dependencies()

    test_cmd = detect_test_command()
    framework_name = "pytest" if "pytest" in str(test_cmd) else test_cmd[0]

    # TF3: On retries, only re-run failing tests for speed
    if retry_mode and "pytest" in str(test_cmd):
        test_cmd = test_cmd + ["--lf"]
        print(f"\n[TDD Loop] Running {framework_name} (last-failed only)...")
    else:
        print(f"\n[TDD Loop] Running {framework_name} Suite...")

    try:
        result = subprocess.run(
            test_cmd,
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            print(f"✅ {framework_name} Tests Passed!")
            print(result.stdout)
            return True, result.stdout
        else:
            print(f"❌ {framework_name} test failures detected:")
            feedback = truncate_feedback(result.stdout + "\n" + result.stderr)
            print(feedback)
            return False, feedback
    except subprocess.TimeoutExpired as e:
        print(f"❌ {framework_name} timed out after 120 seconds")
        return False, f"{framework_name} timed out: {e}"
    except Exception as e:
        print(f"Failed to execute {framework_name}: {e}")
        return False, str(e)


def send_webhook_notification(message: str) -> None:
    """E7: Sends a notification to Slack/Discord if WEBHOOK_URL is configured."""
    webhook_url = os.getenv("WEBHOOK_URL")
    if not webhook_url:
        return
    try:
        # Discord and Slack both accept {"content": "..."} / {"text": "..."}
        payload = {"content": message, "text": message}
        requests.post(webhook_url, json=payload, timeout=10)
        print("📨 Webhook notification sent.")
    except Exception as e:
        print(f"⚠️ Webhook notification failed: {e}")


def estimate_gpu_cost(elapsed_seconds: float) -> str:
    """E8: Estimates GPU cost based on platform pricing and elapsed time."""
    try:
        _platform, _ = gpu_platform.select_platform(use_failover=False)
        info = gpu_platform.get_platform_info(_platform)
        cost_str = info.get("cost")
        if not cost_str or info.get("free"):
            return "Free"
        # Parse cost like "$0.30/hr"
        import re as _re
        match = _re.search(r'\$([\d.]+)', cost_str)
        if match:
            hourly = float(match.group(1))
            estimated = (elapsed_seconds / 3600) * hourly
            return f"~${estimated:.4f} ({cost_str})"
        return cost_str
    except Exception as e:
        print(f"⚠️ Cost estimation error: {e}")
        return "Unknown"


def save_rollback_point() -> Optional[str]:
    """Saves a git commit point before AI changes for auto-rollback.
    
    Creates a temporary commit to ensure uncommitted Planner changes 
    (like project_tasks.md) are preserved and not destroyed by reset --hard.
    """
    try:
        # Commit any pending changes (e.g. from Planner) so they aren't lost
        git_run(["git", "add", "."], capture_output=True)
        status = git_run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if status.stdout.strip():
            git_run(["git", "commit", "-m", "chore: pre-iteration state snapshot"], check=False)
            
        result = git_run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
        commit_hash = result.stdout.strip()
        if commit_hash:
            print(f"📌 Rollback point saved: {commit_hash[:8]}")
            return commit_hash
    except Exception as e:
        print(f"⚠️ Failed to save rollback point: {e}")
    return None


def rollback_if_worse(rollback_hash: Optional[str], pre_test_result: bool) -> None:
    """Auto-rollback if AI made things worse."""
    global _deps_installed_hash
    if not rollback_hash or pre_test_result:
        return
    print("⚠️ AI changes made things worse. Rolling back...")
    try:
        # Reset hard to the snapshot commit (wiping only the Engineer's bad generated code)
        git_run(["git", "reset", "--hard", rollback_hash])
        git_run(["git", "clean", "-fd"])  # Remove untracked files generated by Engineer
        # D3: Reset dep cache so requirements.txt changes are re-installed after rollback
        _deps_installed_hash = ""
        print(f"✅ Rolled back to {rollback_hash[:8]}")
    except Exception as e:
        print(f"⚠️ Rollback failed: {e}")


def run_tdd_loop(max_iterations: int = MAX_TDD_ITERATIONS) -> None:
    """Orchestrates the continuous planning, execution, and testing loop.

    Features:
    - TF1: Smart error extraction (assertion errors only)
    - TF2: Progressive retry strategy (escalating context/temperature)
    - TF3: pytest --lf on retries
    - E3: Conversation memory across iterations
    - E7: Webhook notifications
    - D2: Per-task retry cap (MAX_RETRIES_PER_TASK) to prevent one stuck task from consuming all iterations
    """
    print("\n==============================================")
    print(f"🔄 TDD ORCHESTRATOR: ENGAGED (Max Iterations: {max_iterations}, Per-Task Retry Cap: {MAX_RETRIES_PER_TASK})")
    print("==============================================")

    current_feedback = ""
    completed_tasks: List[str] = []
    failed_tasks: List[str] = []
    loop_start = time.time()
    retry_count = 0  # TF2: Track consecutive retries for the same task
    iteration_memory: List[str] = []  # E3: What the LLM tried in previous iterations
    last_coverage_output = ""  # TF4: Reuse coverage stats
    skipped_tasks: List[str] = []  # D2: Tasks skipped after hitting per-task retry cap

    for iteration in range(max_iterations):
        if not os.path.exists("your_project/project_tasks.md"):
            break

        with open("your_project/project_tasks.md", "r") as f:
            tasks = f.readlines()

        all_done = True
        for i, task in enumerate(tasks):
            if "- [ ]" in task:
                all_done = False
                base_task_description = task.replace("- [ ]", "").strip()
                iter_start = time.time()

                print(f"\n==============================================")
                print(f"🔄 ITERATION {iteration + 1}/{max_iterations}")
                is_retry = bool(current_feedback)
                if is_retry:
                    retry_count += 1

                    # D2: Per-task retry cap — skip this task if it's stuck
                    if retry_count > MAX_RETRIES_PER_TASK:
                        print(f"\n⚠️ Task '{base_task_description}' hit retry cap ({MAX_RETRIES_PER_TASK}). Skipping to next task.")
                        skipped_tasks.append(base_task_description)
                        current_feedback = ""
                        retry_count = 0
                        iteration_memory = []
                        break  # Move to next outer iteration which re-reads tasks

                    # TF1: Extract only the key failures for concise feedback
                    concise_feedback = extract_test_failures(current_feedback)
                    print(f"🎯 PURPOSE: Fixing failing tests for '{base_task_description}' (retry #{retry_count}/{MAX_RETRIES_PER_TASK})")

                    # TF2: Progressive retry strategy
                    test_files_context = ""
                    source_files_context = ""
                    for root, _, files in os.walk("your_project"):
                        for tf in files:
                            file_full = os.path.join(root, tf)
                            if tf.startswith("test_") and (tf.endswith(".py") or tf.endswith(".js") or tf.endswith(".ts") or tf.endswith(".go")):
                                try:
                                    with open(file_full, "r") as ff:
                                        test_files_context += f"\n--- TEST FILE: {file_full} ---\n{ff.read()}\n"
                                except Exception:
                                    pass
                            elif tf.endswith(".py") and not tf.startswith("__") and 'conftest' not in tf:
                                try:
                                    with open(file_full, "r") as ff:
                                        source_files_context += f"\n--- SOURCE FILE: {file_full} ---\n{ff.read()}\n"
                                except Exception:
                                    pass

                    if retry_count == 1:
                        task_prompt = (
                            f"FIX PREVIOUS BUG For Task: '{base_task_description}'.\n"
                            f"Test failures:\n{concise_feedback}\n\n"
                            f"Here are ALL the source and test files you previously generated that FAILED:\n"
                            f"{source_files_context}\n{test_files_context}\n\n"
                            f"RULES: Do NOT include English prose inside .py files. "
                            f"Use 'from app import X' NOT 'from your_project.app import X'. "
                            f"Always generate requirements.txt with ALL dependencies."
                        )
                    elif retry_count == 2:
                        task_prompt = (
                            f"FIX PREVIOUS BUG For Task: '{base_task_description}'.\n"
                            f"Test failures persist:\n{concise_feedback}\n\n"
                            f"HERE IS YOUR PREVIOUS BROKEN CODE (fix it, don't regenerate from scratch):\n"
                            f"{source_files_context}\n{test_files_context}\n\n"
                            f"RULES: Every line in .py files must be valid Python. No English sentences. "
                            f"Use 'from app import X' NOT 'from your_project.app import X'. "
                            f"Generate requirements.txt."
                        )
                    else:
                        # Retry 3+: Include conversation memory + expand context
                        memory_text = "\n".join(f"- Attempt {j+1}: {m}" for j, m in enumerate(iteration_memory[-3:]))
                        task_prompt = (
                            f"FIX PREVIOUS BUG For Task: '{base_task_description}'.\n"
                            f"Test failures:\n{concise_feedback}\n\n"
                            f"IMPORTANT: Previous {retry_count} fix attempts did NOT work. Here is what was tried:\n{memory_text}\n\n"
                            f"HERE IS YOUR PREVIOUS BROKEN CODE:\n{source_files_context}\n{test_files_context}\n\n"
                            f"Try a COMPLETELY DIFFERENT approach. Do NOT repeat previous mistakes.\n"
                            f"RULES: Every line in .py files must be valid Python. No English sentences. "
                            f"Use 'from app import X' NOT 'from your_project.app import X'. "
                            f"Generate requirements.txt."
                        )

                    # E3: Record what we're about to try
                    iteration_memory.append(f"Fixing '{base_task_description}' - errors: {concise_feedback[:200]}")
                else:
                    retry_count = 0
                    iteration_memory = []
                    print(f"🎯 PURPOSE: Implementing new task: '{base_task_description}'")
                    task_prompt = base_task_description
                print("==============================================\n")

                rollback_hash = save_rollback_point()
                files_written = execute_task(task_prompt, use_cache=is_retry, base_task=base_task_description)

                # CG7: If LLM produced zero valid files, skip pytest entirely
                if files_written == 0:
                    print("⚠️ LLM generated 0 valid files. Skipping test validation for this iteration.")
                    rollback_if_worse(rollback_hash, False)
                    current_feedback = "LLM failed to generate any valid code files. All providers may be rate-limited or unavailable."
                    break

                # D4: Auto-create conftest.py to fix import issues
                conftest_path = os.path.join("your_project", "conftest.py")
                if not os.path.exists(conftest_path):
                    with open(conftest_path, "w") as cf:
                        cf.write("import sys, os\nsys.path.insert(0, os.path.dirname(__file__))\n")
                    print("📄 Created conftest.py for clean imports")

                # CG8: Pre-pytest scan — delete any syntax-broken .py files
                for root, _, pfiles in os.walk("your_project"):
                    for pf in pfiles:
                        if pf.endswith(".py") and not pf.startswith("__"):
                            full_path = os.path.join(root, pf)
                            try:
                                with open(full_path, "r", encoding="utf-8", errors="ignore") as fcheck:
                                    ast_module.parse(fcheck.read())
                            except SyntaxError:
                                print(f"❌ Deleting syntax-broken file before pytest: {full_path}")
                                os.remove(full_path)

                # TF3: Use --lf on retries to only re-run failing tests
                success, feedback = run_pytest_validation(retry_mode=is_retry)
                if success:
                    # Run Visual QA if HTML files exist
                    try:
                        import scripts.visual_qa as visual_qa
                        vqa_results = visual_qa.run_visual_qa()
                        for vr in vqa_results:
                            if not vr.get("passed", True):
                                print(f"\n👁 Visual QA failed for {vr['file']}: {vr['feedback'][:200]}")
                                current_feedback = f"Visual QA failed for {vr['file']}. Feedback: {vr['feedback']}"
                                success = False
                                break
                    except Exception as e:
                        print(f"⚠️ Visual QA skipped: {e}")

                elapsed = time.time() - iter_start
                if success:
                    tasks[i] = task.replace("- [ ]", "- [x]")
                    with open("your_project/project_tasks.md", "w") as f:
                        f.writelines(tasks)
                    print(f"✅ Marked Task as Complete: {base_task_description}")
                    print(f"⏱ Iteration {iteration + 1} completed in {elapsed:.1f}s")
                    completed_tasks.append(base_task_description)
                    last_coverage_output = feedback  # TF4: Save for reuse

                    status_text = "".join(tasks)
                    print("\n📈 CURRENT PROJECT STATUS:")
                    print(status_text)

                    step_summary_file = os.getenv("GITHUB_STEP_SUMMARY")
                    if step_summary_file and os.path.exists(step_summary_file):
                        with open(step_summary_file, "a") as f:
                            f.write(f"### Iteration {iteration + 1} Update: Completed `{base_task_description}` ({elapsed:.1f}s)\n\n")
                            f.write(status_text + "\n\n")
                            
                    current_feedback = ""
                    retry_count = 0
                    iteration_memory = []
                else:
                    rollback_if_worse(rollback_hash, False)
                    print(f"⚠️ Task Failed Validation. Iteration {iteration + 1} took {elapsed:.1f}s — will retry.")
                    failed_tasks.append(base_task_description)
                    current_feedback = feedback

                break  # One task per loop iteration

        if all_done:
            print("\n==============================================")
            print("🎉 ALL TASKS COMPLETE AND TESTS PASS. TDD PIPELINE FINISHED.")
            print("==============================================")
            break
    else:
        print(f"\n⚠️ TDD loop exhausted max {max_iterations} iterations without resolving all tasks.")
        post_help_comment()

    total_elapsed = time.time() - loop_start
    print(f"\n⏱ Total TDD loop time: {total_elapsed:.1f}s")
    generate_run_summary(completed_tasks, failed_tasks, total_elapsed, last_coverage_output)

    # E7: Wire webhook notification
    summary_msg = f"🤖 TDD Pipeline: {len(completed_tasks)} completed, {len(failed_tasks)} failed in {total_elapsed:.1f}s"
    send_webhook_notification(summary_msg)


def generate_run_summary(completed: List[str], failed: List[str], total_elapsed: float,
                         last_test_output: str = "") -> None:
    """Generates a docs/run_summary.md report after each pipeline run.

    TF4: Reuses coverage stats from the last test run instead of re-running pytest.
    """
    summary_path = "your_project/docs/run_summary.md"
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)

    # TF4: Parse coverage and test stats from reused output instead of re-running
    coverage_pct = "N/A"
    test_pass_rate = "N/A"
    source = last_test_output if last_test_output else ""

    if not source:
        # Fallback: run pytest only if we don't have cached output
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "your_project/", "--cov=your_project/", "--cov-report=term-missing", "-q"],
                capture_output=True, text=True, timeout=60,
            )
            source = result.stdout
        except Exception:
            pass

    for line in source.split("\n"):
        if "TOTAL" in line and "%" in line:
            coverage_pct = line.split()[-1]
        if "passed" in line:
            test_pass_rate = line.strip()

    from datetime import datetime
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    content = (
        f"# Pipeline Run Summary\n\n"
        f"**Run Time:** {run_time}\n"
        f"**Total Elapsed:** {total_elapsed:.1f}s\n"
        f"**Coverage:** {coverage_pct}\n"
        f"**Test Results:** {test_pass_rate}\n\n"
        f"## Completed Tasks ({len(completed)})\n"
    )
    for t in completed:
        content += f"- ✅ {t}\n"
    content += f"\n## Failed / Retried Tasks ({len(failed)})\n"
    for t in failed:
        content += f"- ❌ {t}\n"
    if not failed:
        content += "- None\n"

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"📝 Run summary saved to {summary_path}")


def post_help_comment() -> None:
    """Posts a PR comment asking for human help when the TDD loop is stuck."""
    pr_number = os.getenv("PR_NUMBER") or os.getenv("ISSUE_NUMBER")
    repo_name = os.getenv("REPO_NAME") or os.getenv("GITHUB_REPOSITORY")
    token = os.getenv("TARGET_REPO_TOKEN") or os.getenv("GITHUB_TOKEN")

    if not all([pr_number, repo_name, token]):
        print("💡 Tip: To enable interactive help, set GITHUB_TOKEN, PR_NUMBER, and REPO_NAME.")
        return

    try:
        g = get_github_client(token)
        repo = g.get_repo(repo_name)
        pr = repo.get_pull(int(pr_number))

        failing_tasks = ""
        if os.path.exists("your_project/project_tasks.md"):
            with open("your_project/project_tasks.md", "r") as f:
                failing_tasks = f.read()

        help_message = (
            "🤖 **AI TDD Orchestrator Needs Your Help!**\n\n"
            "I've tried my best but I'm stuck on the following tasks after 5 iterations:\n\n"
            f"```\n{failing_tasks}\n```\n\n"
            "**How to help:** Reply to this comment with `@ai-hint` followed by your guidance. "
            "For example:\n\n"
            "`@ai-hint The login function should use bcrypt for password hashing, not SHA256.`\n\n"
            "I will automatically resume with your hint injected into the prompt!"
        )
        pr.create_issue_comment(help_message)
        print("✅ Posted help request comment on PR.")
    except Exception as e:
        print(f"⚠️ Could not post help comment: {e}")


def resume_with_hint() -> None:
    """Resumes the TDD loop with a user-provided hint from a PR comment."""
    user_hint = os.getenv("USER_HINT", "")

    if not user_hint:
        print("❌ No USER_HINT environment variable provided.")
        return

    hint_text = user_hint.replace("@ai-hint", "").strip()
    print(f"\n💡 Received user hint: {hint_text}")

    if not os.path.exists("your_project/project_tasks.md"):
        print("⚠️ No project_tasks.md found. Cannot resume.")
        return

    with open("your_project/project_tasks.md", "r") as f:
        tasks = f.readlines()

    for i, task in enumerate(tasks):
        if "- [ ]" in task:
            task_description = task.replace("- [ ]", "").strip()
            enhanced_task = f"{task_description}\n\nUSER HINT: {hint_text}"
            print(f"\n[Resume] Retrying task with hint: {task_description}")
            execute_task(enhanced_task)

            success, feedback = run_pytest_validation()
            if success:
                tasks[i] = task.replace("- [ ]", "- [x]")
                with open("your_project/project_tasks.md", "w") as f:
                    f.writelines(tasks)
                print("✅ Task resolved with user hint!")
            else:
                print(f"⚠️ Task still failing after hint. Feedback: {feedback[:200]}")
            break

    run_tdd_loop()
    push_to_target_repository()

# ---------------------------------------------------------------------------
# Autonomous Issue Resolution
# ---------------------------------------------------------------------------

def resolve_issue() -> None:
    """Autonomous hook to fix a GitHub issue and open a Pull Request."""
    issue_num = os.getenv("ISSUE_NUMBER")
    issue_title = os.getenv("ISSUE_TITLE")
    issue_body = os.getenv("ISSUE_BODY")
    repo_name = os.getenv("REPO_NAME")
    token = os.getenv("TARGET_REPO_TOKEN") or os.getenv("GITHUB_TOKEN")

    if not all([issue_num, issue_title, repo_name, token]):
        print("❌ Missing required environment variables for autonomous issue resolution.")
        print(f"ISSUE_NUMBER={issue_num}, ISSUE_TITLE={issue_title}, REPO_NAME={repo_name}, TOKEN={'Set' if token else 'Not Set'}")
        sys.exit(1)

    branch_name = f"fix-issue-{issue_num}"
    setup_target_repository()

    print(f"\n[Issue Resolver] Creating branch {branch_name}...")
    try:
        git_run(["git", "checkout", "-b", branch_name], check=True)
    except Exception as e:
        print(f"⚠️ Failed to checkout branch {branch_name}: {e}")

    task_prompt = f"Fix GitHub Issue #{issue_num}: {issue_title}\n\nDescription:\n{issue_body}"
    
    if not os.path.exists("your_project/project_tasks.md"):
        print("\n[Issue Resolver] Generating Task Plan from Issue...")
        ensure_code_exists()
        generate_task_plan(task_prompt)
    else:
        print("\n[Issue Resolver] Updating Task Plan with new Issue requirements...")
        update_task_plan(task_prompt)
        
    run_tdd_loop()

    print(f"\n[Issue Resolver] Pushing changes and creating Pull Request...")
    try:
        git_run(["git", "add", "."], check=True)
        status = git_run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if not status.stdout.strip():
            print("✅ Issue was already resolved or no changes generated.")
            sys.exit(0)

        git_run(["git", "commit", "-m", f"fix: Automatically resolve issue #{issue_num}"], check=True)

        remote_url = f"https://oauth2:{token}@github.com/{repo_name}.git"
        git_run(["git", "remote", "set-url", "origin", remote_url], check=False)
        git_run(["git", "push", "-f", "-u", "origin", branch_name], check=True)

        g = get_github_client(token)
        repo = g.get_repo(repo_name)
        pr_body = (
            f"🤖 **Automated AI Pull Request**\n\n"
            f"This PR was autonomously generated to resolve Issue #{issue_num}.\n\n"
            f"- It analyzed the issue: `{issue_title}`\n"
            f"- It passed the 90% Code Coverage Ephemeral TDD validations.\n"
            f"- Please review carefully before merging!\n"
            f"\nResolves #{issue_num}"
        )
        pr = repo.create_pull(
            title=f"Fix issue #{issue_num}: {issue_title}",
            body=pr_body, head=branch_name, base="main",
        )
        print(f"✅ Created Pull Request: {pr.html_url}")
    except Exception as e:
        print(f"❌ Failed to submit automated fix for issue: {mask_secret(str(e), token)}")
        sys.exit(1)

# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    if os.path.exists("prompt.txt"):
        with open("prompt.txt", "r") as f:
            prompt_text = f.read().strip()
        print("\n==============================================")
        print("📄 INITIAL PROMPT (SYSTEM REQUEST):")
        print("==============================================")
        print(prompt_text)
        print("==============================================\n")

    if "--dry-run" in sys.argv:
        print("🏜️  DRY RUN MODE — no code will be generated or pushed.")

    if len(sys.argv) > 1 and sys.argv[1] == "--manual":
        setup_target_repository()
        
        prompt_text = "Build a python app."
        if os.path.exists("prompt.txt"):
            with open("prompt.txt", "r") as f:
                prompt_text = f.read().strip()

        if not os.path.exists("your_project/project_tasks.md"):
            ensure_code_exists()
            generate_task_plan(prompt_text)
        else:
            print("\n🔄 Existing project detected. Updating tasks based on the new prompt...")
            update_task_plan(prompt_text)
            
        run_tdd_loop()
        if not DRY_RUN:
            push_to_target_repository()
    elif len(sys.argv) > 1 and sys.argv[1] == "--issue":
        resolve_issue()
    elif len(sys.argv) > 1 and sys.argv[1] == "--resume-with-hint":
        resume_with_hint()
    elif len(sys.argv) > 1 and sys.argv[1] == "--index-docs":
        print("\n📚 Manually indexing reference documents...")
        count = rag_engine.get_rag_context("test query")
        engine = rag_engine._engine
        if engine:
            print(f"✅ {len(engine.chunks)} chunks indexed from {engine.docs_dir}")
        else:
            print("⚠️ No reference documents found. Place files in your_project/docs/reference/")
    else:
        print("Standard static review pipeline disabled in favor of TDD Orchestrator.")


if __name__ == "__main__":
    main()
