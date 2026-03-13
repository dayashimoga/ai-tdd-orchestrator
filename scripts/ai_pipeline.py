"""AI Orchestrator Pipeline — Professional Edition.

A clean delegator for autonomous AI orchestrators (CrewAI, OpenHands, PydanticAI, Aider).
"""
import os
import sys

# Add project root to sys.path for robust imports
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import scripts.ephemeral_runner as ephemeral_runner
import scripts.git_persistence as git_persistence

# Configuration
PROJECT_DIR = os.getenv("TARGET_PROJECT_DIR", "your_project")
TARGET_REPO_URL = os.getenv("TARGET_REPO_URL")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USER = os.getenv("GITHUB_USER", "dayashimoga") # Default fallback

def main() -> None:
    """Main CLI delegator."""
    global PROJECT_DIR, TARGET_REPO_URL
    if len(sys.argv) < 2:
        print("\n[INFO] AI Orchestrator Professional Edition")
        print("------------------------------------------")
        print("Usage:")
        print("  python scripts/ai_pipeline.py <mode> [prompt]")
        print("\nAvailable Modes:")
        print("  --crewai      : Run multi-agent team (Planner, Engineer, Reviewer)")
        print("  --openhands   : Run fully autonomous software engineering (Docker)")
        print("  --pydanticai  : Run fast, typed micro-agents")
        print("  --aider       : Run high-efficiency CLI coding agent")
        print("  --langgraph   : Run modular LangGraph workflow")
        print("\nNote: All modes run in disposable environments.")
        return

    mode_flag = sys.argv[1]
    
    # Argument parsing (simple)
    args = sys.argv[2:]
    prompt_text = None
    repo_name = None
    
    i = 0
    while i < len(args):
        if args[i] == "--prompt" and i + 1 < len(args):
            prompt_text = args[i+1]
            i += 2
        elif args[i] == "--repo" and i + 1 < len(args):
            repo_name = args[i+1]
            i += 2
        else:
            # Assume it's part of the prompt if not a flag
            if i == 0 and not args[i].startswith("--"):
                prompt_text = " ".join(args)
                break
            i += 1

    if repo_name:
        PROJECT_DIR = repo_name
        if not TARGET_REPO_URL:
            # Construct a default URL if token is present
            TARGET_REPO_URL = f"https://github.com/{GITHUB_USER}/{repo_name}.git"

    if not prompt_text and os.path.exists("prompt.txt"):
        with open("prompt.txt", "r") as f:
            prompt_text = f.read().strip()
    
    # Final fallback if still empty
    if not prompt_text:
        prompt_text = "Standard software engineering task."

    print(f"INFO: Orchestrator Mode: {mode_flag}")
    print(f"INFO: Target Project: {PROJECT_DIR}")
    print(f"INFO: Repository URL: {TARGET_REPO_URL or 'Local'}")

    # --- STATE CONTINUITY: Pull latest changes ---
    git_persistence.ensure_state_continuity(PROJECT_DIR, TARGET_REPO_URL, GITHUB_TOKEN)

    if mode_flag == "--crewai":
        ephemeral_runner.run_ephemeral_orchestration(prompt_text, mode="venv", orchestrator="crewai")
    elif mode_flag == "--openhands":
        ephemeral_runner.run_ephemeral_orchestration(prompt_text, mode="docker", orchestrator="openhands")
    elif mode_flag == "--pydanticai":
        ephemeral_runner.run_ephemeral_orchestration(prompt_text, mode="venv", orchestrator="pydanticai")
    elif mode_flag == "--aider":
        ephemeral_runner.run_ephemeral_orchestration(prompt_text, mode="venv", orchestrator="aider")
    elif mode_flag == "--langgraph":
        ephemeral_runner.run_ephemeral_orchestration(prompt_text, mode="venv", orchestrator="langgraph")
    else:
        print(f"ERROR: Unknown mode: {mode_flag}")
        sys.exit(1)

    # --- PERSISTENCE: Push generated code ---
    commit_msg = f"AI Orchestrator ({mode_flag.strip('--')}): {prompt_text[:50]}..."
    git_persistence.persist_changes(PROJECT_DIR, commit_msg)

if __name__ == "__main__":
    main()
