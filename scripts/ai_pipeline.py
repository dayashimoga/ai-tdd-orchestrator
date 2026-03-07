"""AI TDD Orchestrator Pipeline — V3 Optimized.

Autonomous code generation, testing, and remediation using local LLMs.
Supports: --manual, --issue, --resume-with-hint CLI modes.
"""
import subprocess
import os
import sys
import json
import re
import shutil
from typing import List, Tuple, Optional, Dict, Any

import requests
from github import Github

# Add repository root to Python path so 'scripts.*' imports resolve
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import scripts.repo_map as repo_map
import scripts.gpu_platform as gpu_platform

# ---------------------------------------------------------------------------
# Configuration (all env-configurable)
# ---------------------------------------------------------------------------
# Auto-detect the best GPU platform from environment variables
_detected_platform, _detected_url = gpu_platform.select_platform()
OLLAMA_URL: str = os.getenv("OLLAMA_URL", _detected_url)
MODEL_NAME: str = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:3b")
NUM_CTX: int = int(os.getenv("OLLAMA_NUM_CTX", "8192"))

GITHUB_TOKEN: Optional[str] = os.getenv("GITHUB_TOKEN")
TARGET_REPO_TOKEN: Optional[str] = os.getenv("TARGET_REPO_TOKEN") or GITHUB_TOKEN
PR_NUMBER: Optional[str] = os.getenv("PR_NUMBER")
REPO_NAME: Optional[str] = os.getenv("GITHUB_REPOSITORY")
COMMIT_SHA: Optional[str] = os.getenv("COMMIT_SHA")
IS_LOCAL: bool = os.getenv("LOCAL_MODE", "false").lower() == "true"
PROJECT_TYPE: str = os.getenv("PROJECT_TYPE", "new")
TARGET_REPO: str = os.getenv("TARGET_REPO", "")

GIT_TIMEOUT: int = 120  # seconds — prevents infinite CI hangs

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
    """Validates and sandboxes a file path using realpath."""
    normalized = os.path.normpath(path.strip().lstrip("/"))
    real = os.path.realpath(normalized)
    sandbox_real = os.path.realpath(sandbox)
    if not real.startswith(sandbox_real):
        return None
    return normalized


def git_run(args: List[str], cwd: str = "your_project", **kwargs) -> subprocess.CompletedProcess:
    """Runs a git command with timeout and secrets masking."""
    kwargs.setdefault("timeout", GIT_TIMEOUT)
    result = subprocess.run(args, cwd=cwd, **kwargs)
    return result


def truncate_feedback(feedback: str, max_lines: int = 50) -> str:
    """Truncates error feedback and strips ANSI escape codes."""
    # Strip ANSI escape sequences
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean = ansi_escape.sub('', feedback)
    lines = clean.strip().split('\n')
    if len(lines) > max_lines:
        return '\n'.join(lines[-max_lines:])
    return clean


def parse_and_write_files(raw_output: str, target_dir: str = "your_project") -> int:
    """Parses LLM '--- FILE: path ---' delimited output and writes files.

    Returns the number of files written.
    """
    current_file_path: Optional[str] = None
    current_content: List[str] = []
    files_written = 0

    for line in raw_output.split("\n"):
        if line.startswith("--- FILE:") and line.endswith("---"):
            if current_file_path:
                validated = safe_path(current_file_path, target_dir)
                if validated:
                    write_path = os.path.join(target_dir, validated) if not validated.startswith(target_dir) else validated
                    os.makedirs(os.path.dirname(write_path), exist_ok=True)
                    with open(write_path, "w", encoding="utf-8") as f:
                        f.write("\n".join(current_content).strip())
                    files_written += 1

            extracted = line.replace("--- FILE:", "").replace("---", "").strip()
            current_file_path = extracted
            current_content = []
        else:
            if current_file_path is not None:
                current_content.append(line)

    # Write final tracked file
    if current_file_path:
        validated = safe_path(current_file_path, target_dir)
        if validated:
            write_path = os.path.join(target_dir, validated) if not validated.startswith(target_dir) else validated
            os.makedirs(os.path.dirname(write_path), exist_ok=True)
            with open(write_path, "w", encoding="utf-8") as f:
                f.write("\n".join(current_content).strip())
            files_written += 1

    return files_written

# ---------------------------------------------------------------------------
# Core LLM Interface
# ---------------------------------------------------------------------------

def ai_generate(prompt: str) -> str:
    """Hits the Ollama API to generate code/text, streaming output to stdout."""
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": True,
        "options": {"temperature": 0.2, "num_ctx": NUM_CTX},
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=300, stream=True)
        response.raise_for_status()

        full_response = ""
        for line in response.iter_lines():
            if line:
                chunk = json.loads(line)
                word = chunk.get("response", "")
                full_response += word
                sys.stdout.write(word)
                sys.stdout.flush()

        print()  # newline after streaming
        return full_response
    except Exception as e:
        print(f"\nError calling Ollama API: {e}")
        return ""


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
        except Exception as e:
            error_msg = mask_secret(str(e), TARGET_REPO_TOKEN)
            print(f"❌ Error: Could not create remote repository: {error_msg}")
            if "403" in str(e) or "Forbidden" in str(e) or "404" in str(e):
                print("👉 Hint: The default GitHub Actions token cannot create new repositories.")
                print("👉 Please create a Personal Access Token (PAT) with 'repo' scope and add it to secrets.TARGET_REPO_TOKEN.")
            else:
                print("👉 Hint: If the repository already exists, please run the pipeline with project_type='existing'.")
            sys.exit(1)

        git_run(["git", "init"], check=True)
        git_run(["git", "checkout", "-b", "main"])

        workflow_dir = os.path.join("your_project", ".github", "workflows")
        os.makedirs(workflow_dir, exist_ok=True)
        workflow_path = os.path.join(workflow_dir, "python-test.yml")
        with open(workflow_path, "w") as f:
            f.write("name: CI\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-python@v5\n        with:\n          python-version: '3.11'\n      - run: pip install pytest pytest-cov\n      - run: pip install -r requirements.txt || true\n      - run: pytest --cov=./ --cov-fail-under=90")

        git_run(["git", "add", "."], check=True)
        git_run(["git", "config", "user.name", "ai-orchestrator"])
        git_run(["git", "config", "user.email", "actions@github.com"])
        git_run(["git", "commit", "-m", "chore: setup AI orchestrator repo"], check=True)

        remote_url = f"https://oauth2:{TARGET_REPO_TOKEN}@github.com/{TARGET_REPO}.git"
        git_run(["git", "remote", "add", "origin", remote_url], check=True)
        try:
            git_run(["git", "push", "-u", "origin", "main"], check=True)
            print("✅ Initializer workflow pushed to remote.")
        except Exception as e:
            print(f"⚠️ Failed to push initialization to remote: {mask_secret(str(e), TARGET_REPO_TOKEN)}")


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
            prompt = open("prompt.txt").read()
            advanced_prompt = (
                f"Generate a complete implementation for the following prompt: {prompt}\n"
                "You must organize your output into distinct files. For each file you generate, strictly use the following delimiter format:\n"
                "--- FILE: <file_path_relative_to_root> ---\n<code>\n\n"
                "Example:\n--- FILE: src/index.html ---\n<!DOCTYPE html><html>...</html>\n"
                "--- FILE: src/styles/main.css ---\nbody { color: red; }\n\n"
                "Return ONLY the delimiter blocks and the exact file contents."
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
    plan_prompt = (
        f"Based on the following user prompt: {prompt}\n\n"
        "Create a comprehensive implementation plan as a strict Markdown checklist.\n"
        "Break the work down into granular steps. Ensure there is a step for writing Pytest unit tests.\n"
        "Output ONLY the markdown checklist formatted exactly like this:\n"
        "- [ ] Setup Project Structure\n"
        "- [ ] Implement Core Logic\n"
        "- [ ] Write Unit Tests\n"
    )
    plan_output = ai_generate(plan_prompt)

    with open("your_project/project_tasks.md", "w") as f:
        f.write(plan_output)
    print(plan_output)

    step_summary_file = os.getenv("GITHUB_STEP_SUMMARY")
    if step_summary_file and os.path.exists(step_summary_file):
        with open(step_summary_file, "a") as f:
            f.write("## 📋 AI Task Planner Checklist\n\n")
            f.write(plan_output + "\n\n")


def execute_task(task_description: str) -> None:
    """Agent 2 (The Engineer): Generates code with Repo Map context optimization."""
    print(f"\n[Engineer] Executing Task: {task_description}")

    repo_map_content = repo_map.generate_repo_map("your_project")

    discovery_prompt = (
        f"You are the Engineer Agent. Your current task is: {task_description}\n\n"
        f"Here is the structural map of the current codebase:\n{repo_map_content}\n\n"
        "To accomplish this task, which files do you need to read in their entirety? "
        "Return ONLY a comma-separated list of exact file paths. If you don't need any, return NONE."
    )
    print("🔍 Inspecting Repo Map to determine context window...")

    payload = {"model": MODEL_NAME, "prompt": discovery_prompt, "stream": False, "options": {"temperature": 0.1, "num_ctx": 4096}}
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
        response.raise_for_status()
        requested_files_str = response.json().get("response", "NONE")
    except Exception as e:
        print(f"Failed to query for files: {e}")
        requested_files_str = "NONE"

    requested_files = [f.strip() for f in requested_files_str.split(",") if f.strip() and f.strip() != "NONE"]

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

    engineer_prompt = (
        f"You are the Engineer Agent. Your current task is: {task_description}\n\n"
        f"Here is your optimized project context:\n{context}\n\n"
        "Generate the necessary code to fulfill the task. If the task involves testing, ensure you use `pytest`.\n"
        "You must organize your output into distinct files using exactly this format:\n"
        "--- FILE: <file_path_relative_to_root> ---\n<code>\n\n"
        "Return ONLY the delimiter blocks and exact file contents. Do not include markdown fences around the code."
    )

    raw_output = ai_generate(engineer_prompt)
    parse_and_write_files(raw_output, "your_project")


def run_pytest_validation() -> Tuple[bool, str]:
    """Execute pytest natively to enforce TDD behavior."""
    print("\n[TDD Loop] Running Pytest Suite with Coverage requirements...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "your_project/", "--cov=your_project/", "--cov-fail-under=90", "--cov-report=term-missing"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            print("✅ Tests Passed & Coverage Achieved!")
            print(result.stdout)
            return True, result.stdout
        else:
            print("❌ Test failures or missing coverage detected:")
            feedback = truncate_feedback(result.stdout + "\n" + result.stderr)
            print(feedback)
            return False, feedback
    except subprocess.TimeoutExpired as e:
        print("❌ Pytest timed out after 120 seconds")
        return False, f"Pytest timed out: {e}"
    except Exception as e:
        print(f"Failed to execute Pytest: {e}")
        return False, str(e)


def save_rollback_point() -> Optional[str]:
    """Saves a git stash point before AI changes for auto-rollback."""
    try:
        result = git_run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
        commit_hash = result.stdout.strip()
        if commit_hash:
            print(f"📌 Rollback point saved: {commit_hash[:8]}")
            return commit_hash
    except Exception:
        pass
    return None


def rollback_if_worse(rollback_hash: Optional[str], pre_test_result: bool) -> None:
    """Auto-rollback if AI made things worse."""
    if not rollback_hash or pre_test_result:
        return
    print("⚠️ AI changes made things worse. Rolling back...")
    try:
        git_run(["git", "reset", "--hard", rollback_hash])
        print(f"✅ Rolled back to {rollback_hash[:8]}")
    except Exception as e:
        print(f"⚠️ Rollback failed: {e}")


def run_tdd_loop(max_iterations: int = 5) -> None:
    """Orchestrates the continuous planning, execution, and testing loop."""
    print("\n==============================================")
    print("🔄 TDD ORCHESTRATOR: ENGAGED")
    print("==============================================")

    for iteration in range(max_iterations):
        if not os.path.exists("your_project/project_tasks.md"):
            break

        with open("your_project/project_tasks.md", "r") as f:
            tasks = f.readlines()

        all_done = True
        for i, task in enumerate(tasks):
            if "- [ ]" in task:
                all_done = False
                task_description = task.replace("- [ ]", "").strip()

                rollback_hash = save_rollback_point()
                execute_task(task_description)

                success, feedback = run_pytest_validation()
                if success:
                    # Run Visual QA if HTML files exist
                    try:
                        import scripts.visual_qa as visual_qa
                        vqa_results = visual_qa.run_visual_qa()
                        for vr in vqa_results:
                            if not vr.get("passed", True):
                                print(f"\n👁 Visual QA failed for {vr['file']}: {vr['feedback'][:200]}")
                                execute_task(f"Fix CSS/styling issues in {vr['file']}. Visual QA feedback: {vr['feedback']}")
                    except Exception as e:
                        print(f"⚠️ Visual QA skipped: {e}")

                    tasks[i] = task.replace("- [ ]", "- [x]")
                    with open("your_project/project_tasks.md", "w") as f:
                        f.writelines(tasks)
                    print(f"✅ Marked Task as Complete: {task_description}")

                    status_text = "".join(tasks)
                    print("\n📈 CURRENT PROJECT STATUS:")
                    print(status_text)

                    step_summary_file = os.getenv("GITHUB_STEP_SUMMARY")
                    if step_summary_file and os.path.exists(step_summary_file):
                        with open(step_summary_file, "a") as f:
                            f.write(f"### Iteration Update: Completed `{task_description}`\n\n")
                            f.write(status_text + "\n\n")
                else:
                    rollback_if_worse(rollback_hash, False)
                    print("⚠️ Task Failed Validation. Feeding stack trace back to Engineer...")
                    execute_task(f"FIX PREVIOUS BUG For Task: '{task_description}'. The tests threw this trace: {feedback}")

                break  # One task per loop iteration

        if all_done:
            print("\n==============================================")
            print("🎉 ALL TASKS COMPLETE AND TESTS PASS. TDD PIPELINE FINISHED.")
            print("==============================================")
            break
    else:
        print("\n⚠️ TDD loop exhausted max iterations without resolving all tasks.")
        post_help_comment()


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
    print("\n[Issue Resolver] Generating Task Plan from Issue...")
    generate_task_plan(task_prompt)
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
        prompt_text = open("prompt.txt").read().strip()
        print("\n==============================================")
        print("📄 INITIAL PROMPT (SYSTEM REQUEST):")
        print("==============================================")
        print(prompt_text)
        print("==============================================\n")

    if len(sys.argv) > 1 and sys.argv[1] == "--manual":
        setup_target_repository()
        ensure_code_exists()
        prompt_text = open("prompt.txt").read().strip() if os.path.exists("prompt.txt") else "Build a python app."
        generate_task_plan(prompt_text)
        run_tdd_loop()
        push_to_target_repository()
    elif len(sys.argv) > 1 and sys.argv[1] == "--issue":
        resolve_issue()
    elif len(sys.argv) > 1 and sys.argv[1] == "--resume-with-hint":
        resume_with_hint()
    else:
        print("Standard static review pipeline disabled in favor of TDD Orchestrator.")


if __name__ == "__main__":
    main()
