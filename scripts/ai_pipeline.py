"""AI Orchestrator Pipeline — Professional Edition.

A clean delegator for autonomous AI orchestrators (CrewAI, OpenHands, PydanticAI, Aider).
"""
import os
import sys
import scripts.ephemeral_runner as ephemeral_runner
import scripts.git_persistence as git_persistence

# Configuration
PROJECT_DIR = os.getenv("TARGET_PROJECT_DIR", "your_project")
TARGET_REPO_URL = os.getenv("TARGET_REPO_URL")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

def main() -> None:
    """Main CLI delegator."""
    if len(sys.argv) < 2:
        print("\n🚀 AI Orchestrator Professional Edition")
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
    
    # Get prompt
    prompt_text = "Standard software engineering task."
    if len(sys.argv) > 2:
        prompt_text = " ".join(sys.argv[2:])
    elif os.path.exists("prompt.txt"):
        with open("prompt.txt", "r") as f:
            prompt_text = f.read().strip()

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
        print(f"❌ Unknown mode: {mode_flag}")
        sys.exit(1)

    # --- PERSISTENCE: Push generated code ---
    commit_msg = f"AI Orchestrator ({mode_flag.strip('--')}): {prompt_text[:50]}..."
    git_persistence.persist_changes(PROJECT_DIR, commit_msg)

if __name__ == "__main__":
    main()
