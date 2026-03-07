import subprocess
import os
import requests
from github import Github

# Local Model Execution parameters
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:3b")

# GitHub Context for Inline Reviews Context
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
TARGET_REPO_TOKEN = os.getenv("TARGET_REPO_TOKEN") or GITHUB_TOKEN
PR_NUMBER = os.getenv("PR_NUMBER")
REPO_NAME = os.getenv("GITHUB_REPOSITORY")
COMMIT_SHA = os.getenv("COMMIT_SHA")
IS_LOCAL = os.getenv("LOCAL_MODE", "false").lower() == "true"
PROJECT_TYPE = os.getenv("PROJECT_TYPE", "new")
TARGET_REPO = os.getenv("TARGET_REPO", "")

def ai_generate(prompt):
    """Hits the local Ollama API to generate code/text, streaming output to stdout."""
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": True,
        "options": {
            "temperature": 0.2,
            "num_ctx": 8192
        }
    }
    try:
        import json
        import sys
        
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
        
        print() # Newline after streaming completes
        return full_response
    except Exception as e:
        print(f"\nError calling Ollama API: {e}")
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
        base_ref = os.getenv("GITHUB_BASE_REF") or "main"
        output = subprocess.check_output(
            ["git", "diff", f"origin/{base_ref}...HEAD", "--name-only"], 
            text=True
        )
        return [f.strip() for f in output.split("\n") if f.strip() and f.startswith("your_project/")]
    except Exception as e:
        print(f"Failed to get modified files: {e}")
        return [os.path.join(r, f) for r, d, fs in os.walk("your_project") for f in fs]

def setup_target_repository():
    """Clones an existing repo or creates a new one."""
    if not TARGET_REPO:
        print("⚠️ No TARGET_REPO provided. Operating locally in 'your_project'.")
        return

    # Clean up workspace
    if os.path.exists("your_project"):
        import shutil
        shutil.rmtree("your_project")

    if PROJECT_TYPE == "existing":
        print(f"🔄 Cloning existing project: {TARGET_REPO}")
        clone_url = f"https://oauth2:{TARGET_REPO_TOKEN}@github.com/{TARGET_REPO}.git"
        subprocess.run(["git", "clone", clone_url, "your_project"], check=True)
        print("✅ Clone complete.")
    else:
        print(f"✨ Creating new project repository: {TARGET_REPO}")
        os.makedirs("your_project", exist_ok=True)
        try:
            g = Github(TARGET_REPO_TOKEN)
            user = g.get_user()
            repo_name = TARGET_REPO.split("/")[-1]
            repo = user.create_repo(repo_name, private=True)
            print(f"✅ Created remote repository: {repo.html_url}")
        except Exception as e:
            print(f"❌ Error: Could not create remote repository '{repo_name}': {e}")
            if "403" in str(e) or "Forbidden" in str(e) or "404" in str(e):
                print("👉 Hint: The default GitHub Actions token cannot create new repositories.")
                print("👉 Please create a Personal Access Token (PAT) with 'repo' scope and add it to secrets.TARGET_REPO_TOKEN.")
            else:
                print("👉 Hint: If the repository already exists, please run the pipeline with project_type='existing'.")
            import sys
            sys.exit(1)

        # Initialize local git
        subprocess.run(["git", "init"], cwd="your_project", check=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd="your_project")
        
        # Add basic workflow for new repo testing
        workflow_dir = os.path.join("your_project", ".github", "workflows")
        os.makedirs(workflow_dir, exist_ok=True)
        workflow_path = os.path.join(workflow_dir, "python-test.yml")
        with open(workflow_path, "w") as f:
            f.write("name: CI\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-python@v5\n        with:\n          python-version: '3.11'\n      - run: pip install pytest pytest-cov\n      - run: pip install -r requirements.txt || true\n      - run: pytest --cov=./ --cov-fail-under=90")
        
        subprocess.run(["git", "add", "."], cwd="your_project", check=True)
        subprocess.run(["git", "config", "user.name", "ai-orchestrator"], cwd="your_project")
        subprocess.run(["git", "config", "user.email", "actions@github.com"], cwd="your_project")
        subprocess.run(["git", "commit", "-m", "chore: setup AI orchestrator repo"], cwd="your_project", check=True)
        
        # Connect remote and push
        remote_url = f"https://oauth2:{TARGET_REPO_TOKEN}@github.com/{TARGET_REPO}.git"
        subprocess.run(["git", "remote", "add", "origin", remote_url], cwd="your_project", check=True)
        try:
            subprocess.run(["git", "push", "-u", "origin", "main"], cwd="your_project", check=True)
            print("✅ Initializer workflow pushed to remote.")
        except Exception as e:
            print(f"⚠️ Failed to push initialization to remote: {e}")

def push_to_target_repository():
    """Commits and pushes changes directly to the target repo."""
    if not TARGET_REPO:
        return
        
    print(f"\n🚀 Pushing completed AI generation to {TARGET_REPO} ...")
    try:
        subprocess.run(["git", "config", "user.name", "ai-orchestrator"], cwd="your_project")
        subprocess.run(["git", "config", "user.email", "actions@github.com"], cwd="your_project")
        subprocess.run(["git", "add", "."], cwd="your_project", check=True)
        
        # Check if there is anything to commit
        status = subprocess.run(["git", "status", "--porcelain"], cwd="your_project", capture_output=True, text=True)
        if not status.stdout.strip():
            print("✅ No changes to commit.")
            return

        commit_msg = "feat: autonomous AI generation and TDD fixes"
        subprocess.run(["git", "commit", "-m", commit_msg], cwd="your_project", check=True)
        
        # If it's an existing project, we might need to pull first to avoid conflicts, though we expect AI runs in isolated branches
        remote_url = f"https://oauth2:{TARGET_REPO_TOKEN}@github.com/{TARGET_REPO}.git"
        
        # Ensure remote exists in existing clone
        remotes = subprocess.run(["git", "remote", "-v"], cwd="your_project", capture_output=True, text=True).stdout
        if "origin" not in remotes:
             subprocess.run(["git", "remote", "add", "origin", remote_url], cwd="your_project", check=True)
        else:
             subprocess.run(["git", "remote", "set-url", "origin", remote_url], cwd="your_project", check=True)
             
        subprocess.run(["git", "push", "origin", "main"], cwd="your_project", check=True)
        print("✅ Successfully pushed AI generated code to target repository.")
    except Exception as e:
        print(f"❌ Failed to commit and push changes: {e}")

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
            print("\n==============================================")
            print("🚀 SOFTWARE FACTORY: BOOTSTRAPPING SCAFFOLD")
            print("==============================================")
            print(f"📄 INITIAL PROMPT:\n{prompt.strip()}")
            print("==============================================\n")
            print("🧠 AI is currently designing the multi-file architecture and writing the codebase. Please wait...\n")
            
            raw_output = ai_generate(advanced_prompt)
            print("✅ AI Codebase Generation Complete. Synchronizing files to disk...\n")
            
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
# Autonomous TDD & Task Planning Workflow
# =========================================================================

def generate_task_plan(prompt):
    """
    Agent 1 (The Planner): Reads the prompt and generates a strict Markdown task checklist.
    """
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
    
    # Broadcast to GitHub UI if available
    step_summary_file = os.getenv("GITHUB_STEP_SUMMARY")
    if step_summary_file and os.path.exists(step_summary_file):
        with open(step_summary_file, "a") as f:
            f.write("## 📋 AI Task Planner Checklist\n\n")
            f.write(plan_output + "\n\n")

def execute_task(task_description):
    """
    Agent 2 (The Engineer): Generates implementation code and tests for a specific task.
    """
    print(f"\n[Engineer] Executing Task: {task_description}")
    
    # Read current state of project to provide context
    context = ""
    for root, _, files in os.walk("your_project"):
        for file in files:
            if file.endswith(('.py', '.html', '.css', '.js')):
                with open(os.path.join(root, file), 'r', encoding='utf-8', errors='ignore') as f:
                    context += f"\n--- FILE: {os.path.join(root, file)} ---\n{f.read()}\n"

    engineer_prompt = (
        f"You are the Engineer Agent. Your current task is: {task_description}\n\n"
        f"Here is the current state of the codebase:\n{context}\n\n"
        "Generate the necessary code to fulfill the task. If the task involves testing, ensure you use `pytest`.\n"
        "You must organize your output into distinct files using exactly this format:\n"
        "--- FILE: <file_path_relative_to_root> ---\n<code>\n\n"
        "Return ONLY the delimiter blocks and exact file contents. Do not include markdown fences around the code."
    )
    
    raw_output = ai_generate(engineer_prompt)
    
    # Parse and write files
    current_file_path = None
    current_content = []
    
    for line in raw_output.split("\n"):
        if line.startswith("--- FILE:") and line.endswith("---"):
            if current_file_path:
                normalized_path = os.path.normpath(current_file_path.strip().lstrip('/'))
                write_path = os.path.join("your_project", normalized_path)
                os.makedirs(os.path.dirname(write_path), exist_ok=True)
                with open(write_path, "w", encoding='utf-8') as f:
                    f.write("\n".join(current_content).strip())
            
            extracted_path = line.replace("--- FILE:", "").replace("---", "").strip()
            if ".." in extracted_path: 
                extracted_path = extracted_path.replace("..", "")
                
            current_file_path = extracted_path
            current_content = []
        else:
            if current_file_path is not None:
                current_content.append(line)
                
    if current_file_path:
        normalized_path = os.path.normpath(current_file_path.strip().lstrip('/'))
        write_path = os.path.join("your_project", normalized_path)
        os.makedirs(os.path.dirname(write_path), exist_ok=True)
        with open(write_path, "w", encoding='utf-8') as f:
            f.write("\n".join(current_content).strip())

def run_pytest_validation():
    """Execute pytest natively to enforce TDD behavior."""
    print("\n[TDD Loop] Running Pytest Suite with Coverage requirements...")
    try:
        # Run pytest enforcing 90% coverage
        result = subprocess.run(
            ["python", "-m", "pytest", "your_project/", "--cov=your_project/", "--cov-fail-under=90", "--cov-report=term-missing"],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            print("✅ Tests Passed & Coverage Achieved!")
            print(result.stdout)
            return True, result.stdout
        else:
            print("❌ Test failures or missing coverage detected:")
            print(result.stdout)
            print(result.stderr)
            return False, result.stdout + "\n" + result.stderr
    except subprocess.TimeoutExpired as e:
        print(f"❌ Pytest timed out after 60 seconds")
        timeout_msg = f"Pytest timed out executing the suite: {e}"
        return False, timeout_msg
    except Exception as e:
        print(f"Failed to execute Pytest: {e}")
        return False, str(e)

def run_tdd_loop(max_iterations=5):
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
                
                # Execute the code generation
                execute_task(task_description)
                
                # TDD Feedback Evaluation
                success, feedback = run_pytest_validation()
                if success:
                    # Mark task as complete
                    tasks[i] = task.replace("- [ ]", "- [x]")
                    with open("your_project/project_tasks.md", "w") as f:
                        f.writelines(tasks)
                    print(f"✅ Marked Task as Complete: {task_description}")
                    
                    # Print full CI log tracking
                    status_text = "".join(tasks)
                    print("\n📈 CURRENT PROJECT STATUS:")
                    print(status_text)
                    
                    # Live Update GitHub UI 
                    step_summary_file = os.getenv("GITHUB_STEP_SUMMARY")
                    if step_summary_file and os.path.exists(step_summary_file):
                        with open(step_summary_file, "a") as f:
                            f.write(f"### Iteration Update: Completed `{task_description}`\n\n")
                            f.write(status_text + "\n\n")
                else:
                    print(f"⚠️ Task Failed Validation. Feeding stack trace back to Engineer...")
                    execute_task(f"FIX PREVIOUS BUG For Task: '{task_description}'. The tests threw this trace: {feedback}")
                
                break # Only process one task per loop iteration
                
        if all_done:
            print("\n==============================================")
            print("🎉 ALL TASKS COMPLETE AND TESTS PASS. TDD PIPELINE FINISHED.")
            print("==============================================")
            break

import sys

def main():
    if os.path.exists("prompt.txt"):
        prompt_text = open("prompt.txt").read().strip()
        print("\n==============================================")
        print("📄 INITIAL PROMPT (SYSTEM REQUEST):")
        print("==============================================")
        print(prompt_text)
        print("==============================================\n")
        
    if len(sys.argv) > 1 and sys.argv[1] == "--manual":
        # New Autonomous Mode (Scaffold -> Plan -> TDD Loop)
        setup_target_repository()
        ensure_code_exists()
        prompt_text = open("prompt.txt").read().strip() if os.path.exists("prompt.txt") else "Build a python app."
        generate_task_plan(prompt_text)
        run_tdd_loop()
        push_to_target_repository()
    else:
        print("Standard static review pipeline disabled in favor of TDD Orchestrator.")

if __name__ == "__main__":
    main()
