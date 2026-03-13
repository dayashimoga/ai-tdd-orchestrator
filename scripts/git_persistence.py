import os
import subprocess
import sys
import requests
from typing import Optional

def run_git_command(args: list, cwd: str = ".") -> str:
    """Executes a git command and returns the output."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        # Don't print error if it's a routine check failure (like rev-parse)
        if args[0] not in ["rev-parse", "config", "remote"]:
            print(f"ERROR: Git command failed: {' '.join(args)}")
            print(f"ERROR: Git error: {e.stderr}")
        return ""

def _inject_pat_into_url(url: str, token: Optional[str]) -> str:
    """Injects the GitHub PAT into the repo URL for authentication."""
    if not token or "github.com" not in url:
        return url
    
    # Handle both https://github.com/user/repo and github.com/user/repo
    if url.startswith("https://"):
        return url.replace("https://", f"https://{token}@")
    elif url.startswith("github.com"):
        return f"https://{token}@{url}"
    return url

def _check_repo_exists_github(url: str, token: Optional[str]) -> bool:
    """Checks if the repository exists on GitHub using the provided token."""
    if "github.com" not in url:
        return True # Assume it exists if not GitHub (local or other)
    
    parts = url.rstrip("/").split("/")
    if len(parts) < 2:
        return False
    
    repo_full_name = f"{parts[-2]}/{parts[-1].replace('.git', '')}"
    api_url = f"https://api.github.com/repos/{repo_full_name}"
    headers = {"Authorization": f"token {token}"} if token else {}
    
    try:
        print(f"DEBUG: Checking if repo exists at {api_url}...")
        resp = requests.get(api_url, headers=headers, timeout=10)
        print(f"DEBUG: GitHub Response: {resp.status_code}")
        return resp.status_code == 200
    except Exception as e:
        print(f"WARN: Failed to check repo existence on GitHub: {e}")
        return False

def _create_repo_github(url: str, token: Optional[str]) -> bool:
    """Creates the repository on GitHub if it doesn't exist."""
    if "github.com" not in url or not token:
        return False
    
    parts = url.rstrip("/").split("/")
    if len(parts) < 2:
        return False
    
    repo_name = parts[-1].replace(".git", "")
    owner = parts[-2]
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {
        "name": repo_name,
        "private": True,
        "auto_init": False
    }

    try:
        print(f"INFO: Attempting to create repository '{repo_name}' on GitHub (as user)...")
        # Try creating as a user repository (POST /user/repos)
        resp = requests.post("https://api.github.com/user/repos", headers=headers, json=payload, timeout=10)
        
        if resp.status_code == 201:
            print(f"DONE: Repository '{repo_name}' created successfully as a user repo.")
            return True
        elif resp.status_code == 422:
            print(f"INFO: Repository '{repo_name}' already exists (or name conflict).")
            return True
        
        # If user repo creation failed with something other than already exists, try org
        print(f"DEBUG: User repo creation returned {resp.status_code}. Checking if '{owner}' is an organization...")
        org_api_url = f"https://api.github.com/orgs/{owner}/repos"
        resp_org = requests.post(org_api_url, headers=headers, json=payload, timeout=10)
        
        if resp_org.status_code == 201:
            print(f"DONE: Repository '{repo_name}' created in organization '{owner}'.")
            return True
        elif resp_org.status_code == 422:
            print(f"INFO: Repository '{repo_name}' already exists in organization '{owner}'.")
            return True
            
        print(f"WARN: Failed to create repo: {resp_org.status_code} - {resp_org.text}")
        return False
    except Exception as e:
        print(f"ERROR: Exception during repo creation: {e}")
        return False

def init_repository(path: str, remote_url: Optional[str] = None, token: Optional[str] = None):
    """Initializes a git repository and sets up the remote with PAT."""
    if not os.path.exists(os.path.join(path, ".git")):
        print(f"INFO: Initializing new Git repository in {path}...")
        run_git_command(["init"], cwd=path)
        
        if remote_url:
            authed_url = _inject_pat_into_url(remote_url, token)
            print(f"INFO: Adding remote origin: {remote_url} (PAT injected)")
            run_git_command(["remote", "add", "origin", authed_url], cwd=path)
    else:
        print(f"DONE: Existing Git repository detected in {path}.")

def persist_changes(path: str, message: str = "AI Orchestrator: Update generated code"):
    """Adds, commits, and pushes changes to the remote repository."""
    if not os.path.isdir(path):
        print(f"WARN: Directory '{path}' not found. Nothing to persist.")
        return

    print(f"INFO: Persisting changes in {path}...")
    
    # Configure user for CI environments if not set
    if not run_git_command(["config", "user.name"], cwd=path):
        run_git_command(["config", "user.name", "AI Orchestrator"], cwd=path)
    if not run_git_command(["config", "user.email"], cwd=path):
        run_git_command(["config", "user.email", "orchestrator@ai.local"], cwd=path)

    # 1. Stage changes
    run_git_command(["add", "."], cwd=path)
    
    # 2. Check if there are changes to commit
    status = run_git_command(["status", "--porcelain"], cwd=path)
    if not status:
        print("INFO: No changes to persist.")
        return
    
    # 3. Commit
    run_git_command(["commit", "-m", message], cwd=path)
    
    # 4. Push (if remote exists)
    remotes = run_git_command(["remote"], cwd=path)
    if "origin" in remotes:
        branch = run_git_command(["rev-parse", "--abbrev-ref", "HEAD"], cwd=path) or "main"
        print(f"INFO: Pushing changes to origin/{branch}...")
        run_git_command(["push", "-u", "origin", branch], cwd=path)
    else:
        print("WARN: No remote 'origin' configured. Skipping push.")

def ensure_state_continuity(path: str, remote_url: Optional[str] = None, token: Optional[str] = None):
    """Smart checkout: Clones if exists on GitHub, otherwise initializes locally."""
    if not remote_url:
        print("INFO: No remote URL provided. Skipping state continuity check.")
        return
    
    authed_url = _inject_pat_into_url(remote_url, token)
    
    if os.path.exists(path) and os.path.exists(os.path.join(path, ".git")):
        print(f"DONE: Existing project space detected in {path}.")
        # Ensure remote URL is up-to-date with token
        run_git_command(["remote", "set-url", "origin", authed_url], cwd=path)
        print(f"INFO: Pulling latest changes into {path}...")
        run_git_command(["pull", "origin", "main"], cwd=path) # Default to main if failure occurs
        return

    # Check if repo exists on GitHub to decide between clone or init
    if _check_repo_exists_github(remote_url, token):
        print(f"INFO: Repository found on GitHub. Cloning into {path}...")
        subprocess.run(["git", "clone", authed_url, path], check=True)
    else:
        print(f"INFO: Repository NOT found on GitHub. Initializing state...")
        if token:
            if _create_repo_github(remote_url, token):
                 # Give GitHub a moment to propagate
                 import time
                 time.sleep(2)
        
        print(f"INFO: Creating local workspace at {path}...")
        os.makedirs(path, exist_ok=True)
        init_repository(path, remote_url, token)

if __name__ == "__main__":
    # Test block
    test_path = "your_project"
    test_token = os.getenv("GITHUB_TOKEN")
    test_url = os.getenv("TARGET_REPO_URL", "https://github.com/dummy/repo")
    
    ensure_state_continuity(test_path, test_url, test_token)
    persist_changes(test_path, "Test commit from AI persistence script")
